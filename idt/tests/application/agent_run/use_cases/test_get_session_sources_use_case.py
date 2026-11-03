"""GetSessionSourcesUseCase — agent-run-source-citations §4.2 처리 순서."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_run.use_cases.get_session_sources_use_case import (
    GetSessionSourcesUseCase,
)
from src.domain.agent_run.entities import AgentRun
from src.domain.agent_run.source_policy import RunSourceItem, SourceKind
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
AGENT = "agent-1"
RUN_1 = "11111111-1111-1111-1111-111111111111"
RUN_2 = "22222222-2222-2222-2222-222222222222"
ITEM = RunSourceItem(SourceKind.DOCUMENT, "a.pdf", "발췌", "doc-1")


def _message(message_id: int, role: MessageRole, turn: int = 1) -> ConversationMessage:
    return ConversationMessage(
        id=MessageId(message_id), user_id=UserId("7"), session_id=SessionId("s1"),
        agent_id=AgentId(AGENT), role=role, content="x", turn_index=TurnIndex(turn),
        created_at=T0,
    )


def _run(run_id: str, user_message_id: int, agent_id: str = AGENT, user_id: str = "7") -> AgentRun:
    return AgentRun(
        id=RunId(run_id), conversation_id="s1", user_id=user_id, agent_id=agent_id,
        llm_model_id=None, user_message_id=user_message_id, status=RunStatus.SUCCESS,
        langgraph_thread_id="t", langsmith_trace_id=None, langsmith_run_url=None,
        token_usage=TokenUsage(0, 0, 0), cost_usd=CostUsd(), llm_call_count=0,
        started_at=T0, ended_at=None, latency_ms=None, error_message=None,
        error_stack=None,
    )


def _use_case(messages, runs, built):
    message_repo = MagicMock()
    message_repo.find_by_session = AsyncMock(return_value=messages)
    run_repo = MagicMock()
    run_repo.find_latest_runs_by_user_messages = AsyncMock(return_value=runs)
    service = MagicMock()
    service.build_for_runs = AsyncMock(return_value=built)
    use_case = GetSessionSourcesUseCase(message_repo, run_repo, service, MagicMock())
    return use_case, message_repo, run_repo, service


async def _execute(use_case):
    return await use_case.execute(
        user_id="7", agent_id=AGENT, session_id="s1", request_id="req",
    )


@pytest.mark.asyncio
class TestExecute:
    async def test_assistant_gets_sources_of_preceding_user_run(self) -> None:
        use_case, message_repo, run_repo, service = _use_case(
            [_message(1, MessageRole.USER), _message(2, MessageRole.ASSISTANT)],
            {1: _run(RUN_1, 1)},
            {RUN_1: [ITEM]},
        )
        dto = await _execute(use_case)

        assert [(i.message_id, i.sources) for i in dto.items] == [(2, [ITEM])]
        assert message_repo.find_by_session.await_args.args == (UserId("7"), SessionId("s1"))
        run_repo.find_latest_runs_by_user_messages.assert_awaited_once_with([1])
        service.build_for_runs.assert_awaited_once_with([RunId(RUN_1)], "req")

    async def test_pairs_by_id_order_even_with_legacy_same_turn_index(self) -> None:
        # turn index 수정 전 데이터: user/assistant 가 같은 turn_index 로 저장됐다.
        messages = [
            _message(4, MessageRole.ASSISTANT, 2), _message(3, MessageRole.USER, 2),
            _message(2, MessageRole.ASSISTANT, 1), _message(1, MessageRole.USER, 1),
        ]
        use_case, *_ = _use_case(
            messages, {1: _run(RUN_1, 1), 3: _run(RUN_2, 3)},
            {RUN_1: [ITEM], RUN_2: [ITEM]},
        )
        dto = await _execute(use_case)
        assert [i.message_id for i in dto.items] == [2, 4]

    async def test_one_user_message_pairs_with_first_answer_only(self) -> None:
        use_case, *_ = _use_case(
            [_message(1, MessageRole.USER), _message(2, MessageRole.ASSISTANT),
             _message(3, MessageRole.ASSISTANT)],
            {1: _run(RUN_1, 1)}, {RUN_1: [ITEM]},
        )
        assert [i.message_id for i in (await _execute(use_case)).items] == [2]

    async def test_runs_of_other_agent_or_user_are_ignored(self) -> None:
        use_case, _, _, service = _use_case(
            [_message(1, MessageRole.USER), _message(2, MessageRole.ASSISTANT),
             _message(3, MessageRole.USER), _message(4, MessageRole.ASSISTANT)],
            {1: _run(RUN_1, 1, agent_id="other"), 3: _run(RUN_2, 3, user_id="8")},
            {},
        )
        dto = await _execute(use_case)
        assert dto.items == []
        service.build_for_runs.assert_awaited_once_with([], "req")

    async def test_message_without_sources_is_omitted(self) -> None:
        use_case, *_ = _use_case(
            [_message(1, MessageRole.USER), _message(2, MessageRole.ASSISTANT)],
            {1: _run(RUN_1, 1)}, {},
        )
        assert (await _execute(use_case)).items == []

    async def test_empty_session_skips_run_lookup(self) -> None:
        use_case, _, run_repo, _ = _use_case([], {}, {})
        dto = await _execute(use_case)
        assert (dto.session_id, dto.items) == ("s1", [])
        run_repo.find_latest_runs_by_user_messages.assert_not_awaited()

    async def test_run_lookup_failure_degrades_to_empty(self) -> None:
        use_case, _, run_repo, _ = _use_case(
            [_message(1, MessageRole.USER), _message(2, MessageRole.ASSISTANT)], {}, {},
        )
        run_repo.find_latest_runs_by_user_messages.side_effect = RuntimeError("x")
        assert (await _execute(use_case)).items == []

    async def test_sources_build_failure_degrades_to_empty(self) -> None:
        # Design §4.2 — 근거 조립 실패는 200 items: [] (정책 단계의 예상 밖 예외 포함).
        use_case, _, _, service = _use_case(
            [_message(1, MessageRole.USER), _message(2, MessageRole.ASSISTANT)],
            {1: _run(RUN_1, 1)}, {},
        )
        service.build_for_runs.side_effect = ValueError("policy bug")
        assert (await _execute(use_case)).items == []

    async def test_message_lookup_failure_propagates(self) -> None:
        use_case, message_repo, *_ = _use_case([], {}, {})
        message_repo.find_by_session.side_effect = RuntimeError("db")
        with pytest.raises(RuntimeError):
            await _execute(use_case)
