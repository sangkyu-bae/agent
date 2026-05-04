"""Tests for conversation repository implementations.

TDD: These tests are written first before implementation.
Uses SQLite in-memory database for testing per CLAUDE.md (mock or test container).
"""
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.domain.conversation.entities import (
    ConversationMessage,
    ConversationSummary,
    MessageId,
    SummaryId,
)
from src.domain.conversation.value_objects import (
    AgentId,
    MessageRole,
    SessionId,
    TurnIndex,
    UserId,
)
from src.infrastructure.persistence.models.base import Base
from src.infrastructure.persistence.repositories.conversation_repository import (
    SQLAlchemyConversationMessageRepository,
)
from src.infrastructure.persistence.repositories.conversation_summary_repository import (
    SQLAlchemyConversationSummaryRepository,
)


@pytest.fixture
async def async_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


class TestSQLAlchemyConversationMessageRepository:
    """Tests for SQLAlchemyConversationMessageRepository."""

    @pytest.mark.asyncio
    async def test_save_new_message(self, async_session: AsyncSession) -> None:
        """Should save a new message and return with assigned ID."""
        repo = SQLAlchemyConversationMessageRepository(async_session)
        message = ConversationMessage(
            id=None,
            user_id=UserId("user-123"),
            session_id=SessionId("session-abc"),
            agent_id=AgentId.super(),
            role=MessageRole.USER,
            content="Hello, world!",
            turn_index=TurnIndex(1),
            created_at=datetime.now(),
        )

        saved = await repo.save(message)

        assert saved.id is not None
        assert saved.id.value > 0
        assert saved.content == "Hello, world!"

    @pytest.mark.asyncio
    async def test_find_by_id(self, async_session: AsyncSession) -> None:
        """Should find message by ID."""
        repo = SQLAlchemyConversationMessageRepository(async_session)
        message = ConversationMessage(
            id=None,
            user_id=UserId("user-123"),
            session_id=SessionId("session-abc"),
            agent_id=AgentId.super(),
            role=MessageRole.USER,
            content="Test message",
            turn_index=TurnIndex(1),
            created_at=datetime.now(),
        )
        saved = await repo.save(message)

        found = await repo.find_by_id(saved.id)

        assert found is not None
        assert found.id == saved.id
        assert found.content == "Test message"

    @pytest.mark.asyncio
    async def test_find_by_id_not_found(self, async_session: AsyncSession) -> None:
        """Should return None when message not found."""
        repo = SQLAlchemyConversationMessageRepository(async_session)

        found = await repo.find_by_id(MessageId(999))

        assert found is None

    @pytest.mark.asyncio
    async def test_find_by_session(self, async_session: AsyncSession) -> None:
        """Should find all messages in a session sorted by turn_index."""
        repo = SQLAlchemyConversationMessageRepository(async_session)
        user_id = UserId("user-123")
        session_id = SessionId("session-abc")

        # Create messages out of order
        for turn in [3, 1, 2]:
            await repo.save(
                ConversationMessage(
                    id=None,
                    user_id=user_id,
                    session_id=session_id,
                    agent_id=AgentId.super(),
                    role=MessageRole.USER,
                    content=f"Message {turn}",
                    turn_index=TurnIndex(turn),
                    created_at=datetime.now(),
                )
            )

        messages = await repo.find_by_session(user_id, session_id)

        assert len(messages) == 3
        assert [m.turn_index.value for m in messages] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_find_by_session_different_sessions(
        self, async_session: AsyncSession
    ) -> None:
        """Should only return messages for the specified session."""
        repo = SQLAlchemyConversationMessageRepository(async_session)
        user_id = UserId("user-123")

        # Create messages in two different sessions
        await repo.save(
            ConversationMessage(
                id=None,
                user_id=user_id,
                session_id=SessionId("session-1"),
                agent_id=AgentId.super(),
                role=MessageRole.USER,
                content="Session 1 message",
                turn_index=TurnIndex(1),
                created_at=datetime.now(),
            )
        )
        await repo.save(
            ConversationMessage(
                id=None,
                user_id=user_id,
                session_id=SessionId("session-2"),
                agent_id=AgentId.super(),
                role=MessageRole.USER,
                content="Session 2 message",
                turn_index=TurnIndex(1),
                created_at=datetime.now(),
            )
        )

        messages = await repo.find_by_session(user_id, SessionId("session-1"))

        assert len(messages) == 1
        assert messages[0].content == "Session 1 message"

    @pytest.mark.asyncio
    async def test_get_message_count(self, async_session: AsyncSession) -> None:
        """Should return correct message count."""
        repo = SQLAlchemyConversationMessageRepository(async_session)
        user_id = UserId("user-123")
        session_id = SessionId("session-abc")

        for turn in range(1, 4):
            await repo.save(
                ConversationMessage(
                    id=None,
                    user_id=user_id,
                    session_id=session_id,
                    agent_id=AgentId.super(),
                    role=MessageRole.USER,
                    content=f"Message {turn}",
                    turn_index=TurnIndex(turn),
                    created_at=datetime.now(),
                )
            )

        count = await repo.get_message_count(user_id, session_id)

        assert count == 3

    @pytest.mark.asyncio
    async def test_delete_by_session(self, async_session: AsyncSession) -> None:
        """Should delete all messages in a session."""
        repo = SQLAlchemyConversationMessageRepository(async_session)
        user_id = UserId("user-123")
        session_id = SessionId("session-abc")

        for turn in range(1, 4):
            await repo.save(
                ConversationMessage(
                    id=None,
                    user_id=user_id,
                    session_id=session_id,
                    agent_id=AgentId.super(),
                    role=MessageRole.USER,
                    content=f"Message {turn}",
                    turn_index=TurnIndex(turn),
                    created_at=datetime.now(),
                )
            )

        deleted = await repo.delete_by_session(user_id, session_id)

        assert deleted == 3
        assert await repo.get_message_count(user_id, session_id) == 0


class TestSQLAlchemyConversationSummaryRepository:
    """Tests for SQLAlchemyConversationSummaryRepository."""

    @pytest.mark.asyncio
    async def test_save_new_summary(self, async_session: AsyncSession) -> None:
        """Should save a new summary and return with assigned ID."""
        repo = SQLAlchemyConversationSummaryRepository(async_session)
        summary = ConversationSummary(
            id=None,
            user_id=UserId("user-123"),
            session_id=SessionId("session-abc"),
            agent_id=AgentId.super(),
            summary_content="User asked about settings.",
            start_turn=TurnIndex(1),
            end_turn=TurnIndex(4),
            created_at=datetime.now(),
        )

        saved = await repo.save(summary)

        assert saved.id is not None
        assert saved.id.value > 0
        assert saved.summary_content == "User asked about settings."

    @pytest.mark.asyncio
    async def test_find_by_id(self, async_session: AsyncSession) -> None:
        """Should find summary by ID."""
        repo = SQLAlchemyConversationSummaryRepository(async_session)
        summary = ConversationSummary(
            id=None,
            user_id=UserId("user-123"),
            session_id=SessionId("session-abc"),
            agent_id=AgentId.super(),
            summary_content="Test summary",
            start_turn=TurnIndex(1),
            end_turn=TurnIndex(3),
            created_at=datetime.now(),
        )
        saved = await repo.save(summary)

        found = await repo.find_by_id(saved.id)

        assert found is not None
        assert found.id == saved.id
        assert found.summary_content == "Test summary"

    @pytest.mark.asyncio
    async def test_find_by_id_not_found(self, async_session: AsyncSession) -> None:
        """Should return None when summary not found."""
        repo = SQLAlchemyConversationSummaryRepository(async_session)

        found = await repo.find_by_id(SummaryId(999))

        assert found is None

    @pytest.mark.asyncio
    async def test_find_by_session(self, async_session: AsyncSession) -> None:
        """Should find all summaries for a session sorted by start_turn."""
        repo = SQLAlchemyConversationSummaryRepository(async_session)
        user_id = UserId("user-123")
        session_id = SessionId("session-abc")

        # Create summaries out of order
        for start in [5, 1]:
            await repo.save(
                ConversationSummary(
                    id=None,
                    user_id=user_id,
                    session_id=session_id,
                    agent_id=AgentId.super(),
                    summary_content=f"Summary starting at {start}",
                    start_turn=TurnIndex(start),
                    end_turn=TurnIndex(start + 2),
                    created_at=datetime.now(),
                )
            )

        summaries = await repo.find_by_session(user_id, session_id)

        assert len(summaries) == 2
        assert [s.start_turn.value for s in summaries] == [1, 5]

    @pytest.mark.asyncio
    async def test_find_latest_by_session(self, async_session: AsyncSession) -> None:
        """Should find the most recent summary (highest end_turn)."""
        repo = SQLAlchemyConversationSummaryRepository(async_session)
        user_id = UserId("user-123")
        session_id = SessionId("session-abc")

        await repo.save(
            ConversationSummary(
                id=None,
                user_id=user_id,
                session_id=session_id,
                agent_id=AgentId.super(),
                summary_content="First summary",
                start_turn=TurnIndex(1),
                end_turn=TurnIndex(4),
                created_at=datetime.now(),
            )
        )
        await repo.save(
            ConversationSummary(
                id=None,
                user_id=user_id,
                session_id=session_id,
                agent_id=AgentId.super(),
                summary_content="Second summary",
                start_turn=TurnIndex(1),
                end_turn=TurnIndex(7),
                created_at=datetime.now(),
            )
        )

        latest = await repo.find_latest_by_session(user_id, session_id)

        assert latest is not None
        assert latest.summary_content == "Second summary"
        assert latest.end_turn.value == 7

    @pytest.mark.asyncio
    async def test_find_latest_by_session_no_summaries(
        self, async_session: AsyncSession
    ) -> None:
        """Should return None when no summaries exist."""
        repo = SQLAlchemyConversationSummaryRepository(async_session)

        latest = await repo.find_latest_by_session(
            UserId("user-123"), SessionId("session-abc")
        )

        assert latest is None

    @pytest.mark.asyncio
    async def test_delete_by_session(self, async_session: AsyncSession) -> None:
        """Should delete all summaries for a session."""
        repo = SQLAlchemyConversationSummaryRepository(async_session)
        user_id = UserId("user-123")
        session_id = SessionId("session-abc")

        await repo.save(
            ConversationSummary(
                id=None,
                user_id=user_id,
                session_id=session_id,
                agent_id=AgentId.super(),
                summary_content="Summary 1",
                start_turn=TurnIndex(1),
                end_turn=TurnIndex(3),
                created_at=datetime.now(),
            )
        )
        await repo.save(
            ConversationSummary(
                id=None,
                user_id=user_id,
                session_id=session_id,
                agent_id=AgentId.super(),
                summary_content="Summary 2",
                start_turn=TurnIndex(1),
                end_turn=TurnIndex(6),
                created_at=datetime.now(),
            )
        )

        deleted = await repo.delete_by_session(user_id, session_id)

        assert deleted == 2
        summaries = await repo.find_by_session(user_id, session_id)
        assert len(summaries) == 0
