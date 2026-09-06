"""WorkflowCompiler 워커 컨텍스트 블록 주입 테스트.

Design Ref: worker-context-injection §4.1 / §8.3 L2 #1~3 —
supervisor만 보던 에이전트 프롬프트와 워커 역할을 워커 react agent에도 주입한다.
주입 순서는 datetime → context → (노드별 기존 지시) 이며 기존 지시는 무변경.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowDefinition
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel

AGENT_PROMPT = "당신은 분기 실적을 조사하는 금융 리서치 에이전트입니다."
SCRAPE_DESC = "웹 페이지를 스크래핑해 원문을 수집한다"
TOC_BLOCK = "[에이전트 지식 위키 목차]\n- (id: w1) 여신 기준\n---\n\n"


def _make_llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o-mini",
        display_name="gpt-4o-mini", description=None,
        api_key_env="OPENAI_API_KEY", max_tokens=128000,
        is_active=True, is_default=True, created_at=now, updated_at=now,
    )


def _workflow(specs: list[tuple[str, str]]) -> WorkflowDefinition:
    """specs: [(tool_id, description), ...]"""
    workers = [
        WorkerDefinition(
            tool_id=tid, worker_id=f"worker_{i}", description=desc, sort_order=i,
        )
        for i, (tid, desc) in enumerate(specs)
    ]
    return WorkflowDefinition(
        supervisor_prompt=AGENT_PROMPT, workers=workers, flow_hint="test",
    )


def _make_compiler(toc_block: str | None = None):
    tool_factory = MagicMock()
    tool_factory.create = MagicMock(return_value=MagicMock())
    # MCP 워커는 create_all_async(비동기) 경로를 탄다.
    tool_factory.create_all_async = AsyncMock(return_value=[MagicMock()])
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = MagicMock()

    provider = None
    if toc_block is not None:
        provider = MagicMock()
        provider.render_block = AsyncMock(return_value=toc_block)

    return WorkflowCompiler(
        tool_factory=tool_factory,
        llm_factory=llm_factory,
        logger=MagicMock(),
        wiki_toc_provider=provider,
    )


async def _compile_capturing(compiler, workflow, agent_id="agent_1"):
    async def _noop_node(state):
        return {}

    with patch(
        "src.application.agent_builder.workflow_compiler.create_agent",
        MagicMock(side_effect=lambda *a, **k: _noop_node),
    ) as mock_react, patch(
        "src.application.agent_builder.workflow_compiler.create_supervisor_node",
        MagicMock(return_value=_noop_node),
    ):
        await compiler.compile(
            workflow, _make_llm_model(), "req-1", agent_id=agent_id,
        )
    return mock_react


class TestGeneralWorkerContextInjection:

    @pytest.mark.asyncio
    async def test_general_worker_receives_agent_prompt_and_role(self):
        """FR-02 — 일반(MCP 포함) 워커도 에이전트 프롬프트와 역할을 받는다."""
        compiler = _make_compiler()
        mock_react = await _compile_capturing(
            compiler, _workflow([("mcp:srv:fetch", SCRAPE_DESC)]),
        )
        prompt = mock_react.call_args.kwargs.get("system_prompt")
        assert prompt is not None
        assert AGENT_PROMPT in prompt
        assert SCRAPE_DESC in prompt

    @pytest.mark.asyncio
    async def test_general_worker_receives_tool_usage_norm(self):
        """FR-06 — 소프트 가드가 워커 프롬프트에 포함된다."""
        compiler = _make_compiler()
        mock_react = await _compile_capturing(
            compiler, _workflow([("mcp:srv:fetch", SCRAPE_DESC)]),
        )
        prompt = mock_react.call_args.kwargs["system_prompt"]
        assert "[도구 사용 규범]" in prompt
        assert "추측" in prompt

    @pytest.mark.asyncio
    async def test_each_worker_gets_its_own_role(self):
        compiler = _make_compiler()
        mock_react = await _compile_capturing(
            compiler,
            _workflow([
                ("mcp:srv:fetch", "스크래핑 담당"),
                ("mcp:srv:summarize", "요약 담당"),
            ]),
        )
        prompts = [c.kwargs.get("system_prompt") for c in mock_react.call_args_list]
        assert all(p is not None for p in prompts)
        assert any("스크래핑 담당" in p for p in prompts)
        assert any("요약 담당" in p for p in prompts)
        # 역할이 서로 섞이지 않는다
        scrape_prompt = next(p for p in prompts if "스크래핑 담당" in p)
        assert "요약 담당" not in scrape_prompt


class TestWikiWorkerOrderPreserved:
    """FR-03 — 자체 지시를 가진 노드는 블록을 앞단에만 받고 기존 지시는 무변경."""

    @pytest.mark.asyncio
    async def test_wiki_worker_keeps_toc_and_instruction(self):
        compiler = _make_compiler(toc_block=TOC_BLOCK)
        mock_react = await _compile_capturing(
            compiler, _workflow([("wiki_read", "위키 열람 담당")]),
        )
        prompt = mock_react.call_args.kwargs["system_prompt"]
        assert TOC_BLOCK in prompt
        assert "wiki_read" in prompt  # 기존 워커 지시 유지
        assert AGENT_PROMPT in prompt  # 신규 컨텍스트 블록

    @pytest.mark.asyncio
    async def test_context_block_precedes_toc_block(self):
        """순서: context → wiki_toc → 기존 지시."""
        compiler = _make_compiler(toc_block=TOC_BLOCK)
        mock_react = await _compile_capturing(
            compiler, _workflow([("wiki_read", "위키 열람 담당")]),
        )
        prompt = mock_react.call_args.kwargs["system_prompt"]
        assert prompt.index("[도구 사용 규범]") < prompt.index(TOC_BLOCK)


class TestFunctionNodeContextInjection:
    """GAP-01 — 자체 프롬프트를 갖는 function 노드에도 컨텍스트 블록 주입 (FR-03)."""

    @pytest.mark.asyncio
    async def test_search_node_receives_worker_context_block(self):
        """search rewrite LLM이 실제 검색어를 쓰므로 에이전트 맥락이 필요하다."""
        from src.domain.agent_builder.schemas import (
            WorkerDefinition, WorkflowDefinition,
        )

        compiler = _make_compiler()
        workflow = WorkflowDefinition(
            supervisor_prompt=AGENT_PROMPT, flow_hint="test",
            workers=[WorkerDefinition(
                tool_id="tavily_search", worker_id="web_worker",
                description="웹에서 최신 시장 자료를 찾는다",
                sort_order=0, category="search",
            )],
        )

        async def _noop_node(state):
            return {}

        target = (
            "src.application.agent_builder.workflow_compiler"
            ".create_search_pipeline_node"
        )
        with patch(target, MagicMock(return_value=_noop_node)) as mock_search, patch(
            "src.application.agent_builder.workflow_compiler.create_supervisor_node",
            MagicMock(return_value=_noop_node),
        ):
            await compiler.compile(
                workflow, _make_llm_model(), "req-1", agent_id="agent_1",
            )

        block = mock_search.call_args.kwargs["worker_context_block"]
        assert AGENT_PROMPT in block
        assert "웹에서 최신 시장 자료를 찾는다" in block

    @pytest.mark.asyncio
    async def test_analysis_node_receives_role_without_tool_norm(self):
        """analysis는 도구가 없으므로 도구 규범 없이 역할만 받는다."""
        from src.domain.agent_builder.schemas import (
            WorkerDefinition, WorkflowDefinition,
        )

        compiler = _make_compiler()
        workflow = WorkflowDefinition(
            supervisor_prompt=AGENT_PROMPT, flow_hint="test",
            workers=[WorkerDefinition(
                tool_id="analysis", worker_id="analysis_worker",
                description="수집된 데이터를 해석한다",
                sort_order=0, category="analysis",
            )],
        )

        async def _noop_node(state):
            return {}

        captured = {}
        original = WorkflowCompiler._create_analysis_node

        def _spy(self, llm, worker_id, system_prompt):
            captured["system_prompt"] = system_prompt
            return _noop_node

        with patch.object(WorkflowCompiler, "_create_analysis_node", _spy), patch(
            "src.application.agent_builder.workflow_compiler.create_supervisor_node",
            MagicMock(return_value=_noop_node),
        ):
            await compiler.compile(
                workflow, _make_llm_model(), "req-1", agent_id="agent_1",
            )

        prompt = captured["system_prompt"]
        assert AGENT_PROMPT in prompt
        assert "수집된 데이터를 해석한다" in prompt
        assert "[도구 사용 규범]" not in prompt
