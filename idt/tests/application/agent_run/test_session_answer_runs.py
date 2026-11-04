"""SessionAnswerRunsResolver — 세션 답변 ↔ 런 연결 (근거·도구 내역 공유).

agent-run-tool-trace Design §9.4 — get_session_sources_use_case 에서 추출했다.
근거 유스케이스 테스트가 같은 동작을 계속 고정한다 (회귀 방지).
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_run.session_answer_runs import SessionAnswerRunsResolver
from src.domain.agent_run.entities import AgentRun
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


def _message(mid: int, role: MessageRole) -> ConversationMessage:
    return ConversationMessage(
        id=MessageId(mid), user_id=UserId("7"), session_id=SessionId("s1"),
        agent_id=AgentId("agent-1"), role=role, content="x", turn_index=TurnIndex(1),
        created_at=T0,
    )


def _run(run_id: str, user_message_id: int, agent_id: str = "agent-1", user_id: str = "7"):
    return AgentRun(
        id=RunId(run_id), conversation_id="s1", user_id=user_id, agent_id=agent_id,
        llm_model_id=None, user_message_id=user_message_id, status=RunStatus.SUCCESS,
        langgraph_thread_id="t", langsmith_trace_id=None, langsmith_run_url=None,
        token_usage=TokenUsage(0, 0, 0), cost_usd=CostUsd(), llm_call_count=0,
        started_at=T0, ended_at=None, latency_ms=None, error_message=None,
        error_stack=None,
    )


def _resolver(messages, runs=None, run_error=None):
    message_repo = MagicMock()
    message_repo.find_by_session = AsyncMock(return_value=messages)
    run_repo = MagicMock()
    run_repo.find_latest_runs_by_user_messages = AsyncMock(
        return_value=runs or {}, side_effect=run_error,
    )
    logger = MagicMock()
    return SessionAnswerRunsResolver(message_repo, run_repo, logger), run_repo, logger


async def _resolve(resolver):
    return await resolver.resolve(
        user_id="7", agent_id="agent-1", session_id="s1", request_id="req",
    )


@pytest.mark.asyncio
class TestResolve:
    async def test_assistant_pairs_with_preceding_user_run(self) -> None:
        resolver, run_repo, _ = _resolver(
            [_message(1, MessageRole.USER), _message(2, MessageRole.ASSISTANT),
             _message(3, MessageRole.USER), _message(4, MessageRole.ASSISTANT)],
            runs={1: _run(RUN_1, 1), 3: _run(RUN_2, 3)},
        )
        pairs = await _resolve(resolver)
        assert [(a, r.id.value) for a, r in pairs] == [(2, RUN_1), (4, RUN_2)]
        assert run_repo.find_latest_runs_by_user_messages.await_args.args[0] == [1, 3]

    async def test_no_pairs_skip_run_lookup(self) -> None:
        resolver, run_repo, _ = _resolver([_message(1, MessageRole.USER)])
        assert await _resolve(resolver) == []
        run_repo.find_latest_runs_by_user_messages.assert_not_awaited()

    async def test_other_agent_or_user_runs_are_dropped(self) -> None:
        resolver, *_ = _resolver(
            [_message(1, MessageRole.USER), _message(2, MessageRole.ASSISTANT),
             _message(3, MessageRole.USER), _message(4, MessageRole.ASSISTANT)],
            runs={1: _run(RUN_1, 1, agent_id="other"), 3: _run(RUN_2, 3, user_id="8")},
        )
        assert await _resolve(resolver) == []

    async def test_user_message_without_run_is_skipped(self) -> None:
        resolver, *_ = _resolver(
            [_message(1, MessageRole.USER), _message(2, MessageRole.ASSISTANT)], runs={},
        )
        assert await _resolve(resolver) == []

    async def test_second_assistant_for_same_user_is_not_paired(self) -> None:
        resolver, *_ = _resolver(
            [_message(1, MessageRole.USER), _message(2, MessageRole.ASSISTANT),
             _message(3, MessageRole.ASSISTANT)],
            runs={1: _run(RUN_1, 1)},
        )
        assert [a for a, _ in await _resolve(resolver)] == [2]

    async def test_run_lookup_failure_returns_empty_and_warns(self) -> None:
        error = RuntimeError("db")
        resolver, _, logger = _resolver(
            [_message(1, MessageRole.USER), _message(2, MessageRole.ASSISTANT)],
            run_error=error,
        )
        assert await _resolve(resolver) == []
        assert logger.warning.call_args.kwargs["exception"] is error

    async def test_message_lookup_failure_propagates(self) -> None:
        resolver, *_ = _resolver([])
        resolver._message_repo.find_by_session.side_effect = RuntimeError("db")
        with pytest.raises(RuntimeError):
            await _resolve(resolver)
