"""에이전트별 히스토리 UseCase 테스트 (AGENT-CHAT-001)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.conversation.history_use_case import ConversationHistoryUseCase
from src.domain.conversation.history_schemas import AgentChatSummary, SessionSummary
from src.domain.conversation.entities import ConversationMessage, MessageId
from src.domain.conversation.value_objects import (
    AgentId,
    MessageRole,
    SessionId,
    TurnIndex,
    UserId,
)


def _make_logger():
    logger = MagicMock()
    logger.info = MagicMock()
    logger.error = MagicMock()
    return logger


def _msg(turn: int, session: str = "s1", agent: str = "super") -> ConversationMessage:
    return ConversationMessage(
        id=MessageId(turn),
        user_id=UserId("u1"),
        session_id=SessionId(session),
        agent_id=AgentId(agent),
        role=MessageRole.USER if turn % 2 == 1 else MessageRole.ASSISTANT,
        content=f"msg-{turn}",
        turn_index=TurnIndex(turn),
        created_at=datetime(2026, 4, 30, 10, turn),
    )


class TestGetAgentsWithHistory:

    @pytest.mark.asyncio
    async def test_returns_agents_with_super_and_custom(self) -> None:
        repo = AsyncMock()
        repo.find_agents_by_user.return_value = [
            AgentChatSummary(
                agent_id="super", agent_name="", session_count=5,
                last_chat_at=datetime(2026, 4, 30),
            ),
            AgentChatSummary(
                agent_id="uuid-abc", agent_name="", session_count=3,
                last_chat_at=datetime(2026, 4, 29),
            ),
        ]
        agent_repo = AsyncMock()
        agent_def = MagicMock()
        agent_def.name = "금융 에이전트"
        agent_repo.find_by_id.return_value = agent_def

        uc = ConversationHistoryUseCase(repo=repo, logger=_make_logger(), agent_repo=agent_repo)
        result = await uc.get_agents_with_history("u1", "req-1")

        assert len(result.agents) == 2
        assert result.agents[0].agent_name == "일반 채팅"
        assert result.agents[1].agent_name == "금융 에이전트"

    @pytest.mark.asyncio
    async def test_empty_for_no_history(self) -> None:
        repo = AsyncMock()
        repo.find_agents_by_user.return_value = []

        uc = ConversationHistoryUseCase(repo=repo, logger=_make_logger())
        result = await uc.get_agents_with_history("u1", "req-1")

        assert result.agents == []

    @pytest.mark.asyncio
    async def test_deleted_agent_fallback_name(self) -> None:
        repo = AsyncMock()
        repo.find_agents_by_user.return_value = [
            AgentChatSummary(
                agent_id="deleted-id", agent_name="", session_count=1,
                last_chat_at=datetime(2026, 4, 30),
            ),
        ]
        agent_repo = AsyncMock()
        agent_repo.find_by_id.return_value = None

        uc = ConversationHistoryUseCase(repo=repo, logger=_make_logger(), agent_repo=agent_repo)
        result = await uc.get_agents_with_history("u1", "req-1")

        assert "삭제된 에이전트" in result.agents[0].agent_name


class TestGetSessionsByAgent:

    @pytest.mark.asyncio
    async def test_returns_sessions_for_agent(self) -> None:
        repo = AsyncMock()
        repo.find_sessions_by_user_and_agent.return_value = [
            SessionSummary.from_raw("s1", 4, "hello", datetime(2026, 4, 30, 10)),
            SessionSummary.from_raw("s2", 2, "world", datetime(2026, 4, 29, 10)),
        ]

        uc = ConversationHistoryUseCase(repo=repo, logger=_make_logger())
        result = await uc.get_sessions_by_agent("u1", "super", "req-1")

        assert result.agent_id == "super"
        assert len(result.sessions) == 2
        assert result.sessions[0].session_id == "s1"

    @pytest.mark.asyncio
    async def test_empty_sessions(self) -> None:
        repo = AsyncMock()
        repo.find_sessions_by_user_and_agent.return_value = []

        uc = ConversationHistoryUseCase(repo=repo, logger=_make_logger())
        result = await uc.get_sessions_by_agent("u1", "uuid-xxx", "req-1")

        assert result.sessions == []


class TestGetMessagesByAgent:

    @pytest.mark.asyncio
    async def test_returns_messages(self) -> None:
        repo = AsyncMock()
        repo.find_by_session.return_value = [_msg(1), _msg(2)]

        uc = ConversationHistoryUseCase(repo=repo, logger=_make_logger())
        result = await uc.get_messages_by_agent("u1", "super", "s1", "req-1")

        assert result.agent_id == "super"
        assert result.session_id == "s1"
        assert len(result.messages) == 2
        assert result.messages[0].turn_index == 1

    @pytest.mark.asyncio
    async def test_empty_messages(self) -> None:
        repo = AsyncMock()
        repo.find_by_session.return_value = []

        uc = ConversationHistoryUseCase(repo=repo, logger=_make_logger())
        result = await uc.get_messages_by_agent("u1", "super", "s1", "req-1")

        assert result.messages == []
