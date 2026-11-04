"""GetSessionToolTracesUseCase — agent-run-tool-trace §4.2 (Plan FR-08~FR-10)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_run.use_cases.get_session_tool_traces_use_case import (
    GetSessionToolTracesUseCase,
)
from src.domain.agent_run.entities import AgentRun
from src.domain.agent_run.tool_trace_policy import (
    ToolTrace,
    ToolTraceItem,
    ToolTraceKind,
)
from src.domain.agent_run.value_objects import CostUsd, RunId, RunStatus, TokenUsage
from src.domain.conversation.entities import (
    AgentId,
    ConversationMessage,
    MessageId,
    MessageRole,
    SessionId,
    TurnIndex,
    UserId,
)

T0 = datetime(2026, 11, 3, tzinfo=timezone.utc)
RUN_1 = "11111111-1111-1111-1111-111111111111"
RUN_2 = "22222222-2222-2222-2222-222222222222"
TRACE = ToolTrace(items=[ToolTraceItem(seq=1, kind=ToolTraceKind.TOOL, label="도구")])


def _message(mid: int, role: MessageRole) -> ConversationMessage:
    return ConversationMessage(
        id=MessageId(mid), user_id=UserId("7"), session_id=SessionId("s1"),
        agent_id=AgentId("agent-1"), role=role, content="x", turn_index=TurnIndex(1),
        created_at=T0,
    )


def _run(run_id: str, user_message_id: int) -> AgentRun:
    return AgentRun(
        id=RunId(run_id), conversation_id="s1", user_id="7", agent_id="agent-1",
        llm_model_id=None, user_message_id=user_message_id, status=RunStatus.SUCCESS,
        langgraph_thread_id="t", langsmith_trace_id=None, langsmith_run_url=None,
        token_usage=TokenUsage(0, 0, 0), cost_usd=CostUsd(), llm_call_count=0,
        started_at=T0, ended_at=None, latency_ms=None, error_message=None,
        error_stack=None,
    )


TWO_TURNS = [
    _message(1, MessageRole.USER), _message(2, MessageRole.ASSISTANT),
    _message(3, MessageRole.USER), _message(4, MessageRole.ASSISTANT),
]


def _use_case(messages, runs, built=None, build_error=None):
    message_repo = MagicMock()
    message_repo.find_by_session = AsyncMock(return_value=messages)
    run_repo = MagicMock()
    run_repo.find_latest_runs_by_user_messages = AsyncMock(return_value=runs)
    service = MagicMock()
    service.build_for_runs = AsyncMock(return_value=built or {}, side_effect=build_error)
    logger = MagicMock()
    use_case = GetSessionToolTracesUseCase(message_repo, run_repo, service, logger)
    return use_case, service, logger


async def _execute(use_case):
    return await use_case.execute(
        user_id="7", agent_id="agent-1", session_id="s1", request_id="req",
    )


@pytest.mark.asyncio
class TestExecute:
    async def test_each_assistant_gets_trace_of_its_run(self) -> None:
        use_case, service, _ = _use_case(
            TWO_TURNS, {1: _run(RUN_1, 1), 3: _run(RUN_2, 3)}, {RUN_2: TRACE},
        )
        dto = await _execute(use_case)
        assert dto.session_id == "s1"
        assert [(i.message_id, i.tool_trace) for i in dto.items] == [(4, TRACE)]
        # 세션 단위 일괄 조회 — 메시지마다 부르지 않는다 (FR-08).
        service.build_for_runs.assert_awaited_once_with([RunId(RUN_1), RunId(RUN_2)], "req")

    async def test_session_without_answers_returns_empty_without_building(self) -> None:
        use_case, service, _ = _use_case([_message(1, MessageRole.USER)], {})
        assert (await _execute(use_case)).items == []
        service.build_for_runs.assert_not_awaited()

    async def test_build_failure_returns_empty_and_warns(self) -> None:
        error = ValueError("policy bug")
        use_case, _, logger = _use_case(TWO_TURNS, {1: _run(RUN_1, 1)}, build_error=error)
        assert (await _execute(use_case)).items == []
        assert logger.warning.call_args.kwargs["exception"] is error

    async def test_message_lookup_failure_propagates(self) -> None:
        use_case, *_ = _use_case([], {})
        use_case._answer_runs._message_repo.find_by_session.side_effect = RuntimeError("db")
        with pytest.raises(RuntimeError):
            await _execute(use_case)
