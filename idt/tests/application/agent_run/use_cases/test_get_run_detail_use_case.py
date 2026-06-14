"""M4-5: GetRunDetailUseCase 단위 테스트.

agent-run-observability-m4 Design §3.1, §9.1.
"""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_run.exceptions import (
    RunAccessDeniedError,
    RunNotFoundError,
)
from src.application.agent_run.use_cases.get_run_detail_use_case import (
    GetRunDetailUseCase,
)
from src.domain.agent_run.entities import (
    AgentRun,
    AgentRunStep,
    LlmCall,
    RetrievalSource,
    ToolCall,
)
from src.domain.agent_run.value_objects import (
    CostUsd,
    NodeType,
    RunId,
    RunStatus,
    StepStatus,
    TokenUsage,
)

RUN_ID = "11111111-1111-1111-1111-111111111111"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_run(user_id: str = "user-1") -> AgentRun:
    return AgentRun(
        id=RunId(RUN_ID),
        conversation_id="conv-1",
        user_id=user_id,
        agent_id="agent-1",
        llm_model_id="m-1",
        user_message_id=1,
        status=RunStatus.SUCCESS,
        langgraph_thread_id="thread-1",
        langsmith_trace_id=None,
        langsmith_run_url=None,
        token_usage=TokenUsage(100, 50, 150),
        cost_usd=CostUsd(),
        llm_call_count=1,
        started_at=_now(),
        ended_at=_now(),
        latency_ms=100,
        error_message=None,
        error_stack=None,
    )


def _make_step(step_id: str, step_index: int, node_name: str = "supervisor") -> AgentRunStep:
    return AgentRunStep(
        id=step_id,
        run_id=RunId(RUN_ID),
        step_index=step_index,
        node_name=node_name,
        node_type=NodeType.SUPERVISOR,
        llm_model_id=None,
        status=StepStatus.SUCCESS,
        input_summary="in",
        output_summary="out",
        started_at=_now(),
        ended_at=_now(),
        latency_ms=50,
        error_text=None,
    )


def _make_tool_call(tc_id: str, step_id: str | None) -> ToolCall:
    return ToolCall(
        id=tc_id,
        run_id=RunId(RUN_ID),
        step_id=step_id,
        tool_name="internal_document_search",
        llm_model_id=None,
        arguments_json={"query": "q"},
        result_summary="res",
        result_json=None,
        token_usage=None,
        total_cost_usd=None,
        latency_ms=200,
        status="SUCCESS",
        error_text=None,
        created_at=_now(),
    )


def _make_retrieval(tc_id: str, chunk_id: str, rank: int) -> RetrievalSource:
    return RetrievalSource(
        id=f"rs-{chunk_id}",
        run_id=RunId(RUN_ID),
        tool_call_id=tc_id,
        collection_name="finance",
        document_id="doc-1",
        chunk_id=chunk_id,
        score=0.9,
        rank_index=rank,
        content_preview="preview",
        metadata_json={"source": "doc1.pdf"},
        created_at=_now(),
    )


def _make_llm_call(
    llm_id: str,
    step_id: str | None,
    tool_call_id: str | None,
) -> LlmCall:
    return LlmCall(
        id=llm_id,
        run_id=RunId(RUN_ID),
        step_id=step_id,
        tool_call_id=tool_call_id,
        user_id="user-1",
        agent_id="agent-1",
        llm_model_id="m-1",
        provider="openai",
        model_name="gpt-4o",
        purpose=None,
        token_usage=TokenUsage(100, 50, 150),
        input_price_per_1k_usd=Decimal("0.005"),
        output_price_per_1k_usd=Decimal("0.015"),
        cost_usd=CostUsd(
            input_usd=Decimal("0.0005"),
            output_usd=Decimal("0.00075"),
            total_usd=Decimal("0.00125"),
        ),
        latency_ms=1200,
        status="SUCCESS",
        error_text=None,
        created_at=_now(),
    )


def _make_use_case(
    run: AgentRun | None,
    steps: list[AgentRunStep] | None = None,
    tool_calls: list[ToolCall] | None = None,
    retrievals: list[RetrievalSource] | None = None,
    llm_calls: list[LlmCall] | None = None,
):
    agent_run_repo = MagicMock()
    agent_run_repo.find_run = AsyncMock(return_value=run)
    agent_run_repo.find_steps = AsyncMock(return_value=steps or [])
    agent_run_repo.find_tool_calls = AsyncMock(return_value=tool_calls or [])
    agent_run_repo.find_retrievals = AsyncMock(return_value=retrievals or [])

    llm_call_repo = MagicMock()
    llm_call_repo.find_by_run = AsyncMock(return_value=llm_calls or [])

    logger = MagicMock()
    return (
        GetRunDetailUseCase(
            agent_run_repo=agent_run_repo,
            llm_call_repo=llm_call_repo,
            logger=logger,
        ),
        agent_run_repo,
        llm_call_repo,
    )


class TestTreeAssembly:
    @pytest.mark.asyncio
    async def test_returns_run_with_steps_tool_calls_retrievals_llm_calls(self):
        run = _make_run()
        step1 = _make_step("step-1", 1)
        tc1 = _make_tool_call("tc-1", "step-1")
        ret1 = _make_retrieval("tc-1", "chunk-1", 1)
        llm_node = _make_llm_call("llm-1", "step-1", None)
        llm_tool = _make_llm_call("llm-2", "step-1", "tc-1")

        uc, _, _ = _make_use_case(
            run=run,
            steps=[step1],
            tool_calls=[tc1],
            retrievals=[ret1],
            llm_calls=[llm_node, llm_tool],
        )
        dto = await uc.execute(RUN_ID, requesting_user_id="user-1", is_admin=False)

        assert dto.run.id.value == RUN_ID
        assert len(dto.steps) == 1
        s = dto.steps[0]
        assert s.step.id == "step-1"
        # 노드 본문 LLM (tool_call_id NULL) = step.llm_calls
        assert len(s.llm_calls) == 1
        assert s.llm_calls[0].id == "llm-1"
        # tool_call 1건
        assert len(s.tool_calls) == 1
        tc_node = s.tool_calls[0]
        assert tc_node.tool_call.id == "tc-1"
        # tool 내부 LLM = tool_call.llm_calls
        assert len(tc_node.llm_calls) == 1
        assert tc_node.llm_calls[0].id == "llm-2"
        # retrieval = tool_call.retrievals
        assert len(tc_node.retrievals) == 1
        assert tc_node.retrievals[0].chunk_id == "chunk-1"

    @pytest.mark.asyncio
    async def test_step_with_no_llm_calls_returns_empty_lists(self):
        run = _make_run()
        step1 = _make_step("step-1", 1)

        uc, _, _ = _make_use_case(run=run, steps=[step1])
        dto = await uc.execute(RUN_ID, requesting_user_id="user-1", is_admin=False)

        assert dto.steps[0].llm_calls == []
        assert dto.steps[0].tool_calls == []

    @pytest.mark.asyncio
    async def test_orphan_llm_calls_with_null_step_id_are_separate(self):
        run = _make_run()
        orphan = _make_llm_call("llm-orphan", None, None)

        uc, _, _ = _make_use_case(run=run, llm_calls=[orphan])
        dto = await uc.execute(RUN_ID, requesting_user_id="user-1", is_admin=False)

        assert len(dto.orphan_llm_calls) == 1
        assert dto.orphan_llm_calls[0].id == "llm-orphan"


class TestPermissions:
    @pytest.mark.asyncio
    async def test_raises_run_not_found_when_run_is_none(self):
        uc, _, _ = _make_use_case(run=None)
        with pytest.raises(RunNotFoundError) as exc:
            await uc.execute(RUN_ID, requesting_user_id="user-1", is_admin=False)
        assert exc.value.run_id == RUN_ID

    @pytest.mark.asyncio
    async def test_raises_access_denied_for_other_user_non_admin(self):
        run = _make_run(user_id="user-OWNER")
        uc, _, _ = _make_use_case(run=run)
        with pytest.raises(RunAccessDeniedError):
            await uc.execute(RUN_ID, requesting_user_id="user-INTRUDER", is_admin=False)

    @pytest.mark.asyncio
    async def test_admin_can_access_other_users_run(self):
        run = _make_run(user_id="user-OWNER")
        uc, _, _ = _make_use_case(run=run)
        dto = await uc.execute(RUN_ID, requesting_user_id="admin-1", is_admin=True)
        assert dto.run.id.value == RUN_ID


class TestNPlusOneGuard:
    @pytest.mark.asyncio
    async def test_uses_exactly_5_repo_calls_max(self):
        """N+1 가드: 트리 조립이 정확히 5회 repo 호출."""
        run = _make_run()
        step1 = _make_step("step-1", 1)
        step2 = _make_step("step-2", 2, node_name="worker")
        tc1 = _make_tool_call("tc-1", "step-1")
        tc2 = _make_tool_call("tc-2", "step-2")
        rets = [_make_retrieval("tc-1", f"c-{i}", i) for i in range(5)]
        llms = [_make_llm_call(f"llm-{i}", "step-1", None) for i in range(3)]

        uc, agent_run_repo, llm_call_repo = _make_use_case(
            run=run,
            steps=[step1, step2],
            tool_calls=[tc1, tc2],
            retrievals=rets,
            llm_calls=llms,
        )
        await uc.execute(RUN_ID, requesting_user_id="user-1", is_admin=False)

        # find_run(1) + find_steps(1) + find_tool_calls(1) + find_retrievals(1) + find_by_run(1) = 5
        assert agent_run_repo.find_run.await_count == 1
        assert agent_run_repo.find_steps.await_count == 1
        assert agent_run_repo.find_tool_calls.await_count == 1
        assert agent_run_repo.find_retrievals.await_count == 1
        assert llm_call_repo.find_by_run.await_count == 1
