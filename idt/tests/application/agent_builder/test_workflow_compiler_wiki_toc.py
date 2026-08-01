"""WorkflowCompiler 위키 목차 주입 테스트 (wiki-agentic-navigation FR-03/FR-04).

D1: wiki_read 워커 존재 + provider 주입 + agent_id 전달 시에만
supervisor 프롬프트 prepend + wiki_read 워커 react agent prompt 이중 주입.
그 외 경로는 바이트 단위 불변(무회귀).
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowDefinition
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel

TOC_BLOCK = "[에이전트 지식 위키 목차]\n- (id: w1) 여신/한도 산정 기준 — 갱신 2026-07-23\n---\n\n"


def _make_llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o-mini",
        display_name="gpt-4o-mini", description=None,
        api_key_env="OPENAI_API_KEY", max_tokens=128000,
        is_active=True, is_default=True, created_at=now, updated_at=now,
    )


def _workflow(tool_ids: list[str]) -> WorkflowDefinition:
    workers = [
        WorkerDefinition(
            tool_id=tid, worker_id=f"worker_{i}", description=f"워커 {i}",
            sort_order=i,
        )
        for i, tid in enumerate(tool_ids)
    ]
    return WorkflowDefinition(
        supervisor_prompt="당신은 AI 에이전트입니다.", workers=workers,
        flow_hint="test",
    )


def _make_compiler(toc_block: str | None = TOC_BLOCK):
    tool_factory = MagicMock()
    tool_factory.create = MagicMock(return_value=MagicMock())
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = MagicMock()

    provider = None
    if toc_block is not None:
        provider = MagicMock()
        provider.render_block = AsyncMock(return_value=toc_block)

    compiler = WorkflowCompiler(
        tool_factory=tool_factory,
        llm_factory=llm_factory,
        logger=MagicMock(),
        wiki_toc_provider=provider,
    )
    return compiler, provider


async def _compile_capturing(compiler, workflow, agent_id):
    """compile 후 (supervisor_prompt, react agent 호출 목록) 반환.

    langgraph add_node는 노드 함수를 inspect하므로 Mock 반환값 대신
    실제 async 함수를 돌려준다(Mock의 가짜 __code__가 TypeError 유발).
    """

    async def _noop_node(state):
        return {}

    with patch(
        "src.application.agent_builder.workflow_compiler.create_react_agent",
        MagicMock(side_effect=lambda *a, **k: _noop_node),
    ) as mock_react, patch(
        "src.application.agent_builder.workflow_compiler.create_supervisor_node",
        MagicMock(return_value=_noop_node),
    ) as mock_sup:
        await compiler.compile(
            workflow, _make_llm_model(), "req-1", agent_id=agent_id,
        )
    sup_prompt = mock_sup.call_args.kwargs["supervisor_prompt"]
    return sup_prompt, mock_react


class TestTocInjected:

    @pytest.mark.asyncio
    async def test_supervisor_prompt_contains_toc_block(self):
        compiler, provider = _make_compiler()
        sup_prompt, _ = await _compile_capturing(
            compiler, _workflow(["wiki_read"]), agent_id="agent_1",
        )
        assert TOC_BLOCK in sup_prompt
        assert sup_prompt.endswith("당신은 AI 에이전트입니다.")
        provider.render_block.assert_awaited_once_with("agent_1", "req-1")

    @pytest.mark.asyncio
    async def test_wiki_worker_react_agent_gets_prompt(self):
        compiler, _ = _make_compiler()
        _, mock_react = await _compile_capturing(
            compiler, _workflow(["wiki_read"]), agent_id="agent_1",
        )
        prompt = mock_react.call_args.kwargs.get("prompt")
        assert prompt is not None and TOC_BLOCK in prompt
        assert "wiki_read" in prompt  # 워커 사용 지시 포함

    @pytest.mark.asyncio
    async def test_non_wiki_worker_react_agent_has_no_prompt(self):
        """wiki_read 외 워커(react 경로)는 prompt 미주입 — 기존 동작 불변."""
        compiler, _ = _make_compiler()
        _, mock_react = await _compile_capturing(
            compiler, _workflow(["wiki_read", "excel_export"]), agent_id="agent_1",
        )
        prompts = [c.kwargs.get("prompt") for c in mock_react.call_args_list]
        assert sum(p is not None for p in prompts) == 1  # wiki_read 워커만


FOLDER_BLOCK = (
    "[에이전트 지식 위키 지도]\n- 여신 — 여신 지식 (3건)\n---\n\n"
)


class TestFolderMode:
    """wiki-folder-summaries D6: 폴더 모드 시 wiki_read 워커에 wiki_list 동봉."""

    @pytest.mark.asyncio
    async def test_folder_block_bundles_wiki_list_tool(self):
        compiler, _ = _make_compiler(toc_block=FOLDER_BLOCK)
        _, mock_react = await _compile_capturing(
            compiler, _workflow(["wiki_read"]), agent_id="agent_1",
        )
        tools = mock_react.call_args.kwargs.get("tools") or mock_react.call_args.args[1]
        assert len(tools) == 2  # wiki_read + wiki_list 동봉
        create_calls = [c.args[0] for c in compiler._tool_factory.create.call_args_list]
        assert "wiki_list" in create_calls

    @pytest.mark.asyncio
    async def test_folder_block_uses_folder_worker_instruction(self):
        compiler, _ = _make_compiler(toc_block=FOLDER_BLOCK)
        _, mock_react = await _compile_capturing(
            compiler, _workflow(["wiki_read"]), agent_id="agent_1",
        )
        prompt = mock_react.call_args.kwargs.get("prompt")
        assert prompt is not None and FOLDER_BLOCK in prompt
        assert "wiki_list" in prompt  # 폴더 모드 지시

    @pytest.mark.asyncio
    async def test_folder_block_also_prepended_to_supervisor(self):
        """D1 이중 주입 계약 — 폴더 모드에서도 supervisor에 같은 블록 prepend."""
        compiler, _ = _make_compiler(toc_block=FOLDER_BLOCK)
        sup_prompt, _ = await _compile_capturing(
            compiler, _workflow(["wiki_read"]), agent_id="agent_1",
        )
        assert FOLDER_BLOCK in sup_prompt
        assert sup_prompt.endswith("당신은 AI 에이전트입니다.")

    @pytest.mark.asyncio
    async def test_flat_block_does_not_bundle_wiki_list(self):
        """flat 목차(기존 모드) — 동봉 없음, 기존 지시 유지."""
        compiler, _ = _make_compiler(toc_block=TOC_BLOCK)
        _, mock_react = await _compile_capturing(
            compiler, _workflow(["wiki_read"]), agent_id="agent_1",
        )
        tools = mock_react.call_args.kwargs.get("tools") or mock_react.call_args.args[1]
        assert len(tools) == 1
        create_calls = [c.args[0] for c in compiler._tool_factory.create.call_args_list]
        assert "wiki_list" not in create_calls

    @pytest.mark.asyncio
    async def test_wiki_list_create_failure_falls_back_to_read_only(self):
        """팩토리 의존 미배선(ValueError) — 동봉 생략하고 wiki_read 단독 진행."""
        compiler, _ = _make_compiler(toc_block=FOLDER_BLOCK)
        original_create = compiler._tool_factory.create

        def _create(tool_id, *args, **kwargs):
            if tool_id == "wiki_list":
                raise ValueError("wiki_list 미배선")
            return MagicMock()

        compiler._tool_factory.create = MagicMock(side_effect=_create)
        _, mock_react = await _compile_capturing(
            compiler, _workflow(["wiki_read"]), agent_id="agent_1",
        )
        tools = mock_react.call_args.kwargs.get("tools") or mock_react.call_args.args[1]
        assert len(tools) == 1  # graceful degradation


class TestTocInactive:

    @pytest.mark.asyncio
    async def test_no_wiki_worker_provider_not_called(self):
        """FR-04: wiki_read 미선택 → provider 미호출 + 프롬프트 불변."""
        compiler, provider = _make_compiler()
        sup_prompt, _ = await _compile_capturing(
            compiler, _workflow(["excel_export"]), agent_id="agent_1",
        )
        provider.render_block.assert_not_awaited()
        assert sup_prompt == "당신은 AI 에이전트입니다."

    @pytest.mark.asyncio
    async def test_no_agent_id_provider_not_called(self):
        """agent_id 미전달(기존 호출부·sub_agent 재귀) → 비활성."""
        compiler, provider = _make_compiler()
        sup_prompt, _ = await _compile_capturing(
            compiler, _workflow(["wiki_read"]), agent_id=None,
        )
        provider.render_block.assert_not_awaited()
        assert sup_prompt == "당신은 AI 에이전트입니다."

    @pytest.mark.asyncio
    async def test_no_provider_compiles_plain(self):
        """provider 미주입(DI 이전 호출부) → 기존 동작."""
        compiler, _ = _make_compiler(toc_block=None)
        sup_prompt, mock_react = await _compile_capturing(
            compiler, _workflow(["wiki_read"]), agent_id="agent_1",
        )
        assert sup_prompt == "당신은 AI 에이전트입니다."
        assert mock_react.call_args.kwargs.get("prompt") is None

    @pytest.mark.asyncio
    async def test_empty_toc_block_no_injection(self):
        """위키 0건(provider가 '' 반환) → 블록·워커 prompt 모두 미주입."""
        compiler, provider = _make_compiler(toc_block="")
        sup_prompt, mock_react = await _compile_capturing(
            compiler, _workflow(["wiki_read"]), agent_id="agent_1",
        )
        provider.render_block.assert_awaited_once()
        assert sup_prompt == "당신은 AI 에이전트입니다."
        assert mock_react.call_args.kwargs.get("prompt") is None
