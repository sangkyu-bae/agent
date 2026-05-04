"""ConversationHistoryUseCase 단위 테스트 (CHAT-HIST-001)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.conversation.entities import ConversationMessage, MessageId
from src.domain.conversation.value_objects import (
    AgentId,
    MessageRole,
    SessionId,
    TurnIndex,
    UserId,
)
from src.domain.conversation.history_schemas import SessionSummary


def _make_use_case(sessions=None, messages=None, raise_on_sessions=None):
    from src.application.conversation.history_use_case import (
        ConversationHistoryUseCase,
    )

    repo = AsyncMock()
    logger = MagicMock()

    if raise_on_sessions is not None:
        repo.find_sessions_by_user.side_effect = raise_on_sessions
    else:
        repo.find_sessions_by_user.return_value = sessions or []

    repo.find_by_session.return_value = messages or []

    uc = ConversationHistoryUseCase(repo=repo, logger=logger)
    return uc, repo, logger


def _msg(turn: int, role: str, content: str, msg_id: int = None) -> ConversationMessage:
    return ConversationMessage(
        id=MessageId(msg_id) if msg_id else None,
        user_id=UserId("u-1"),
        session_id=SessionId("s-1"),
        agent_id=AgentId.super(),
        role=MessageRole.USER if role == "user" else MessageRole.ASSISTANT,
        content=content,
        turn_index=TurnIndex(turn),
        created_at=datetime(2026, 4, 17, 10, 0, turn),
    )


class TestGetSessions:
    @pytest.mark.asyncio
    async def test_returns_sessions_from_repo(self):
        sessions = [
            SessionSummary("s-a", 4, "안녕", datetime(2026, 4, 17, 11)),
            SessionSummary("s-b", 2, "날씨", datetime(2026, 4, 17, 10)),
        ]
        uc, _, _ = _make_use_case(sessions=sessions)

        result = await uc.get_sessions(user_id="u-1", request_id="req-1")

        assert result.user_id == "u-1"
        assert len(result.sessions) == 2
        assert result.sessions[0].session_id == "s-a"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_sessions(self):
        uc, _, _ = _make_use_case(sessions=[])

        result = await uc.get_sessions(user_id="u-1", request_id="req-1")

        assert result.user_id == "u-1"
        assert result.sessions == []


class TestGetMessages:
    @pytest.mark.asyncio
    async def test_returns_messages_sorted_by_turn(self):
        messages = [
            _msg(1, "user", "질문1", msg_id=1),
            _msg(2, "assistant", "답변1", msg_id=2),
        ]
        uc, _, _ = _make_use_case(messages=messages)

        result = await uc.get_messages(
            user_id="u-1", session_id="s-1", request_id="req-1"
        )

        assert result.user_id == "u-1"
        assert result.session_id == "s-1"
        assert len(result.messages) == 2
        assert result.messages[0].turn_index == 1
        assert result.messages[0].role == "user"
        assert result.messages[1].role == "assistant"

    @pytest.mark.asyncio
    async def test_returns_empty_messages_when_session_not_found(self):
        uc, _, _ = _make_use_case(messages=[])

        result = await uc.get_messages(
            user_id="u-1", session_id="unknown", request_id="req-1"
        )

        assert result.messages == []


class TestLogging:
    @pytest.mark.asyncio
    async def test_get_sessions_logs_start_and_completion(self):
        uc, _, logger = _make_use_case(sessions=[])

        await uc.get_sessions(user_id="u-1", request_id="req-1")

        assert logger.info.call_count >= 2

    @pytest.mark.asyncio
    async def test_get_messages_logs_start_and_completion(self):
        uc, _, logger = _make_use_case(messages=[])

        await uc.get_messages(user_id="u-1", session_id="s-1", request_id="req-9")

        assert logger.info.call_count >= 2

    @pytest.mark.asyncio
    async def test_logs_error_and_reraises_on_repo_exception(self):
        uc, _, logger = _make_use_case(raise_on_sessions=RuntimeError("DB 오류"))

        with pytest.raises(RuntimeError):
            await uc.get_sessions(user_id="u-1", request_id="req-1")

        logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_id_propagated_to_logs(self):
        uc, _, logger = _make_use_case(sessions=[])

        await uc.get_sessions(user_id="u-1", request_id="req-xyz")

        # info 호출 중 request_id=req-xyz 가 한 번이라도 포함되어야 함
        assert any(
            call.kwargs.get("request_id") == "req-xyz"
            for call in logger.info.call_args_list
        )
