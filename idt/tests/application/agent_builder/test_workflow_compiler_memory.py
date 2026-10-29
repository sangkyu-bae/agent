"""WorkflowCompiler 메모리 블록 prepend — agent-memory-injection Design §6.1 (C1~C6).

Plan FR-01: 순서 날짜 → 사용자 → 메모리 → wiki 목차 → 본문.
Plan FR-02: include_user_context=False 면 메모리도 생략.
Plan FR-03: 서브에이전트 재귀에는 전달하지 않는다 (depth=0 한정).
Plan FR-06: 미전달이면 변경 전과 프롬프트 바이트 동일.
Plan FR-08: 검색 파이프라인 user_context_block 에 메모리 미포함.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_builder.workflow_compiler import WorkflowCompiler
from src.domain.agent_builder.schemas import WorkerDefinition, WorkflowDefinition
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.entity import LlmModel

_MOD = "src.application.agent_builder.workflow_compiler"
MEMORY = "[사용자 메모리]\n- (용어) ETC = 외부 여신 한도\n---\n\n"
USER = "[사용자 정보]\n부서: 여신팀\n---\n"
DATE = "[현재 날짜]\n2026-10-29\n---\n"
TOC = "[위키 목차]\n- 여신 규정\n---\n"


def _llm_model() -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id="model-1", provider="openai", model_name="gpt-4o-mini",
        display_name="m", description=None, api_key_env="OPENAI_API_KEY",
        max_tokens=128000, is_active=True, is_default=True,
        created_at=now, updated_at=now,
    )


def _workflow(tool_id: str = "tool_0") -> WorkflowDefinition:
    return WorkflowDefinition(
        supervisor_prompt="본문 프롬프트",
        flow_hint="t",
        workers=[WorkerDefinition(
            tool_id=tool_id, worker_id="w0", description="워커", sort_order=0,
        )],
    )


def _compiler(**extra) -> WorkflowCompiler:
    tool_factory = MagicMock()
    tool_factory.create = MagicMock(return_value=MagicMock())
    tool_factory.create_all_async = AsyncMock(return_value=[MagicMock()])
    llm_factory = MagicMock(spec=LLMFactoryInterface)
    llm_factory.create.return_value = MagicMock()
    return WorkflowCompiler(
        tool_factory=tool_factory, llm_factory=llm_factory, logger=MagicMock(), **extra
    )


def _patches(user: str = USER, date: str = DATE):
    """사용자·날짜 렌더를 고정하고 supervisor 노드 생성을 스파이한다."""
    return (
        patch(f"{_MOD}.render_user_context_block", return_value=user),
        patch(f"{_MOD}.render_datetime_block", return_value=date),
        patch(f"{_MOD}.create_agent", return_value=MagicMock()),
        patch(f"{_MOD}.create_supervisor_node", wraps=_real_supervisor_node()),
    )


def _real_supervisor_node():
    from src.application.agent_builder.workflow_compiler import create_supervisor_node

    return create_supervisor_node


async def _compile_and_get_prompt(compiler, workflow, **kwargs) -> str:
    p_user, p_date, p_agent, p_sup = _patches()
    with p_user, p_date, p_agent, p_sup as sup:
        await compiler.compile(workflow, _llm_model(), "req-1", **kwargs)
        return sup.call_args_list[0].kwargs["supervisor_prompt"]


class TestPrependOrder:
    @pytest.mark.asyncio
    async def test_C1_메모리는_사용자_뒤_본문_앞(self):
        prompt = await _compile_and_get_prompt(
            _compiler(), _workflow(), include_user_context=True, memory_block=MEMORY,
        )
        assert prompt == DATE + USER + MEMORY + "본문 프롬프트"

    @pytest.mark.asyncio
    async def test_C2_include_user_context_False면_메모리도_생략(self):
        prompt = await _compile_and_get_prompt(
            _compiler(), _workflow(), include_user_context=False, memory_block=MEMORY,
        )
        assert MEMORY not in prompt
        assert USER not in prompt
        assert prompt == DATE + "본문 프롬프트"

    @pytest.mark.asyncio
    async def test_C3_미전달이면_기존_프롬프트_불변(self):
        prompt = await _compile_and_get_prompt(
            _compiler(), _workflow(), include_user_context=True,
        )
        assert prompt == DATE + USER + "본문 프롬프트"

    @pytest.mark.asyncio
    async def test_C6_날짜_사용자_메모리_목차_본문_순서(self):
        provider = MagicMock()
        provider.render_block = AsyncMock(return_value=TOC)
        compiler = _compiler(wiki_toc_provider=provider)
        prompt = await _compile_and_get_prompt(
            compiler, _workflow(tool_id="wiki_read"),
            include_user_context=True, memory_block=MEMORY, agent_id="ag-1",
        )
        assert prompt == DATE + USER + MEMORY + TOC + "본문 프롬프트"


class TestScopeBoundaries:
    @pytest.mark.asyncio
    async def test_C4_서브에이전트_재귀에는_메모리_미전달(self):
        sub_agent = MagicMock()
        sub_agent.status = "active"
        sub_agent.llm_model_id = "model-1"
        sub_agent.temperature = 0.0
        sub_agent.include_user_context = True
        sub_agent.to_workflow_definition.return_value = _workflow()
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=sub_agent)
        compiler = _compiler(agent_repository=repo)
        parent = WorkflowDefinition(
            supervisor_prompt="부모", flow_hint="t",
            workers=[WorkerDefinition(
                tool_id="sub_agent", worker_id="child", description="서브",
                sort_order=0, worker_type="sub_agent", ref_agent_id="agent-child",
            )],
        )
        p_user, p_date, p_agent, p_sup = _patches()
        with p_user, p_date, p_agent, p_sup as sup, patch.object(
            compiler, "_compile_sub_agent", wraps=compiler._compile_sub_agent,
        ) as sub_spy:
            await compiler.compile(
                parent, _llm_model(), "req-1",
                include_user_context=True, memory_block=MEMORY,
            )
        assert "memory_block" not in sub_spy.call_args.kwargs
        prompts = [c.kwargs["supervisor_prompt"] for c in sup.call_args_list]
        assert len(prompts) == 2
        # 재귀(서브)는 먼저 생성된다 — 메모리는 최상위(부모)에만.
        assert prompts[0] == DATE + USER + "본문 프롬프트"
        assert prompts[1] == DATE + USER + MEMORY + "부모"

    @pytest.mark.asyncio
    async def test_C5_검색_파이프라인_user_context_block에_메모리_없음(self):
        compiler = _compiler()
        p_user, p_date, p_agent, p_sup = _patches()
        with p_user, p_date, p_agent, p_sup, patch.object(
            compiler, "_create_worker_node_for_category",
            wraps=compiler._create_worker_node_for_category,
        ) as node_spy:
            await compiler.compile(
                _workflow(tool_id="internal_document_search"), _llm_model(), "req-1",
                include_user_context=True, memory_block=MEMORY,
            )
        kwargs = node_spy.call_args.kwargs
        assert kwargs["user_context_block"] == USER
        assert MEMORY not in kwargs["user_context_block"]
