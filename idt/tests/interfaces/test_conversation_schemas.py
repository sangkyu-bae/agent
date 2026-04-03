"""Tests for conversation Pydantic schemas.

TDD: These tests are written first before implementation.
"""
from datetime import datetime

import pytest
from pydantic import ValidationError

from src.interfaces.schemas.conversation import (
    ConversationMessageCreate,
    ConversationMessageResponse,
    ConversationMessageListResponse,
    ConversationSummaryCreate,
    ConversationSummaryResponse,
)


class TestConversationMessageCreate:
    """Tests for ConversationMessageCreate schema."""

    def test_valid_user_message(self) -> None:
        """Should create valid user message."""
        msg = ConversationMessageCreate(
            user_id="user-123",
            session_id="session-abc",
            role="user",
            content="Hello, world!",
            turn_index=1,
        )
        assert msg.user_id == "user-123"
        assert msg.session_id == "session-abc"
        assert msg.role == "user"
        assert msg.content == "Hello, world!"
        assert msg.turn_index == 1

    def test_valid_assistant_message(self) -> None:
        """Should create valid assistant message."""
        msg = ConversationMessageCreate(
            user_id="user-123",
            session_id="session-abc",
            role="assistant",
            content="Hello! How can I help?",
            turn_index=2,
        )
        assert msg.role == "assistant"

    def test_invalid_role(self) -> None:
        """Should reject invalid role."""
        with pytest.raises(ValidationError):
            ConversationMessageCreate(
                user_id="user-123",
                session_id="session-abc",
                role="system",  # Invalid
                content="Hello",
                turn_index=1,
            )

    def test_empty_content_rejected(self) -> None:
        """Should reject empty content."""
        with pytest.raises(ValidationError):
            ConversationMessageCreate(
                user_id="user-123",
                session_id="session-abc",
                role="user",
                content="",
                turn_index=1,
            )

    def test_empty_user_id_rejected(self) -> None:
        """Should reject empty user_id."""
        with pytest.raises(ValidationError):
            ConversationMessageCreate(
                user_id="",
                session_id="session-abc",
                role="user",
                content="Hello",
                turn_index=1,
            )

    def test_turn_index_must_be_positive(self) -> None:
        """Should reject non-positive turn_index."""
        with pytest.raises(ValidationError):
            ConversationMessageCreate(
                user_id="user-123",
                session_id="session-abc",
                role="user",
                content="Hello",
                turn_index=0,
            )


class TestConversationMessageResponse:
    """Tests for ConversationMessageResponse schema."""

    def test_response_includes_id(self) -> None:
        """Response should include message ID."""
        now = datetime.now()
        response = ConversationMessageResponse(
            id=1,
            user_id="user-123",
            session_id="session-abc",
            role="user",
            content="Hello",
            turn_index=1,
            created_at=now,
        )
        assert response.id == 1
        assert response.created_at == now

    def test_from_entity(self) -> None:
        """Should be able to create from domain entity data."""
        now = datetime.now()
        response = ConversationMessageResponse(
            id=1,
            user_id="user-123",
            session_id="session-abc",
            role="assistant",
            content="Response",
            turn_index=2,
            created_at=now,
        )
        assert response.role == "assistant"


class TestConversationMessageListResponse:
    """Tests for ConversationMessageListResponse schema."""

    def test_list_response(self) -> None:
        """Should contain list of messages."""
        now = datetime.now()
        messages = [
            ConversationMessageResponse(
                id=1,
                user_id="user-123",
                session_id="session-abc",
                role="user",
                content="Hello",
                turn_index=1,
                created_at=now,
            ),
            ConversationMessageResponse(
                id=2,
                user_id="user-123",
                session_id="session-abc",
                role="assistant",
                content="Hi!",
                turn_index=2,
                created_at=now,
            ),
        ]
        response = ConversationMessageListResponse(
            messages=messages,
            total=2,
        )
        assert len(response.messages) == 2
        assert response.total == 2


class TestConversationSummaryCreate:
    """Tests for ConversationSummaryCreate schema."""

    def test_valid_summary(self) -> None:
        """Should create valid summary."""
        summary = ConversationSummaryCreate(
            user_id="user-123",
            session_id="session-abc",
            summary_content="User discussed settings.",
            start_turn=1,
            end_turn=4,
        )
        assert summary.user_id == "user-123"
        assert summary.summary_content == "User discussed settings."
        assert summary.start_turn == 1
        assert summary.end_turn == 4

    def test_empty_summary_content_rejected(self) -> None:
        """Should reject empty summary content."""
        with pytest.raises(ValidationError):
            ConversationSummaryCreate(
                user_id="user-123",
                session_id="session-abc",
                summary_content="",
                start_turn=1,
                end_turn=4,
            )

    def test_end_turn_must_be_gte_start_turn(self) -> None:
        """Should reject end_turn < start_turn."""
        with pytest.raises(ValidationError):
            ConversationSummaryCreate(
                user_id="user-123",
                session_id="session-abc",
                summary_content="Summary",
                start_turn=5,
                end_turn=3,
            )


class TestConversationSummaryResponse:
    """Tests for ConversationSummaryResponse schema."""

    def test_response_includes_id(self) -> None:
        """Response should include summary ID."""
        now = datetime.now()
        response = ConversationSummaryResponse(
            id=1,
            user_id="user-123",
            session_id="session-abc",
            summary_content="User asked about features.",
            start_turn=1,
            end_turn=4,
            created_at=now,
        )
        assert response.id == 1
        assert response.start_turn == 1
        assert response.end_turn == 4
        assert response.created_at == now
