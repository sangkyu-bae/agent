"""Tests for conversation entities.

TDD: These tests are written first before implementation.
"""
from datetime import datetime

import pytest

from src.domain.conversation.entities import (
    MessageId,
    SummaryId,
    ConversationMessage,
    ConversationSummary,
)
from src.domain.conversation.value_objects import (
    AgentId,
    UserId,
    SessionId,
    TurnIndex,
    MessageRole,
)


class TestMessageId:
    """Tests for MessageId value object."""

    def test_create_valid_message_id(self) -> None:
        message_id = MessageId(1)
        assert message_id.value == 1

    def test_message_id_equality(self) -> None:
        id1 = MessageId(1)
        id2 = MessageId(1)
        assert id1 == id2

    def test_message_id_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="MessageId must be positive"):
            MessageId(0)

    def test_message_id_negative_raises_error(self) -> None:
        with pytest.raises(ValueError, match="MessageId must be positive"):
            MessageId(-1)


class TestSummaryId:
    """Tests for SummaryId value object."""

    def test_create_valid_summary_id(self) -> None:
        summary_id = SummaryId(1)
        assert summary_id.value == 1

    def test_summary_id_equality(self) -> None:
        id1 = SummaryId(1)
        id2 = SummaryId(1)
        assert id1 == id2

    def test_summary_id_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="SummaryId must be positive"):
            SummaryId(0)


class TestConversationMessage:
    """Tests for ConversationMessage entity."""

    def test_create_conversation_message(self) -> None:
        now = datetime.now()
        message = ConversationMessage(
            id=MessageId(1),
            user_id=UserId("user-123"),
            session_id=SessionId("session-abc"),
            agent_id=AgentId.super(),
            role=MessageRole.USER,
            content="Hello, how are you?",
            turn_index=TurnIndex(1),
            created_at=now,
        )
        assert message.id.value == 1
        assert message.user_id.value == "user-123"
        assert message.session_id.value == "session-abc"
        assert message.role == MessageRole.USER
        assert message.content == "Hello, how are you?"
        assert message.turn_index.value == 1
        assert message.created_at == now

    def test_create_message_without_id(self) -> None:
        """New messages may not have an ID until persisted."""
        now = datetime.now()
        message = ConversationMessage(
            id=None,
            user_id=UserId("user-123"),
            session_id=SessionId("session-abc"),
            agent_id=AgentId.super(),
            role=MessageRole.ASSISTANT,
            content="I'm doing well, thank you!",
            turn_index=TurnIndex(2),
            created_at=now,
        )
        assert message.id is None
        assert message.role == MessageRole.ASSISTANT

    def test_message_content_cannot_be_empty(self) -> None:
        with pytest.raises(ValueError, match="Message content cannot be empty"):
            ConversationMessage(
                id=MessageId(1),
                user_id=UserId("user-123"),
                session_id=SessionId("session-abc"),
                agent_id=AgentId.super(),
                role=MessageRole.USER,
                content="",
                turn_index=TurnIndex(1),
                created_at=datetime.now(),
            )

    def test_message_content_whitespace_only_raises_error(self) -> None:
        with pytest.raises(ValueError, match="Message content cannot be empty"):
            ConversationMessage(
                id=MessageId(1),
                user_id=UserId("user-123"),
                session_id=SessionId("session-abc"),
                agent_id=AgentId.super(),
                role=MessageRole.USER,
                content="   ",
                turn_index=TurnIndex(1),
                created_at=datetime.now(),
            )


class TestConversationSummary:
    """Tests for ConversationSummary entity."""

    def test_create_conversation_summary(self) -> None:
        now = datetime.now()
        summary = ConversationSummary(
            id=SummaryId(1),
            user_id=UserId("user-123"),
            session_id=SessionId("session-abc"),
            agent_id=AgentId.super(),
            summary_content="User asked about account settings.",
            start_turn=TurnIndex(1),
            end_turn=TurnIndex(3),
            created_at=now,
        )
        assert summary.id.value == 1
        assert summary.user_id.value == "user-123"
        assert summary.session_id.value == "session-abc"
        assert summary.summary_content == "User asked about account settings."
        assert summary.start_turn.value == 1
        assert summary.end_turn.value == 3
        assert summary.created_at == now

    def test_create_summary_without_id(self) -> None:
        """New summaries may not have an ID until persisted."""
        now = datetime.now()
        summary = ConversationSummary(
            id=None,
            user_id=UserId("user-123"),
            session_id=SessionId("session-abc"),
            agent_id=AgentId.super(),
            summary_content="Discussion about features.",
            start_turn=TurnIndex(1),
            end_turn=TurnIndex(3),
            created_at=now,
        )
        assert summary.id is None

    def test_summary_content_cannot_be_empty(self) -> None:
        with pytest.raises(ValueError, match="Summary content cannot be empty"):
            ConversationSummary(
                id=SummaryId(1),
                user_id=UserId("user-123"),
                session_id=SessionId("session-abc"),
                agent_id=AgentId.super(),
                summary_content="",
                start_turn=TurnIndex(1),
                end_turn=TurnIndex(3),
                created_at=datetime.now(),
            )

    def test_end_turn_must_be_greater_than_or_equal_to_start_turn(self) -> None:
        with pytest.raises(
            ValueError, match="end_turn must be >= start_turn"
        ):
            ConversationSummary(
                id=SummaryId(1),
                user_id=UserId("user-123"),
                session_id=SessionId("session-abc"),
                agent_id=AgentId.super(),
                summary_content="Some summary",
                start_turn=TurnIndex(5),
                end_turn=TurnIndex(3),
                created_at=datetime.now(),
            )

    def test_summary_with_same_start_and_end_turn(self) -> None:
        """Summary can cover a single turn."""
        now = datetime.now()
        summary = ConversationSummary(
            id=SummaryId(1),
            user_id=UserId("user-123"),
            session_id=SessionId("session-abc"),
            agent_id=AgentId.super(),
            summary_content="Single turn summary.",
            start_turn=TurnIndex(3),
            end_turn=TurnIndex(3),
            created_at=now,
        )
        assert summary.start_turn.value == summary.end_turn.value == 3
