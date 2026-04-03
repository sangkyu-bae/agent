"""Tests for conversation value objects.

TDD: These tests are written first before implementation.
"""
import pytest

from src.domain.conversation.value_objects import (
    UserId,
    SessionId,
    TurnIndex,
    MessageRole,
)


class TestUserId:
    """Tests for UserId value object."""

    def test_create_valid_user_id(self) -> None:
        user_id = UserId("user-123")
        assert user_id.value == "user-123"

    def test_user_id_equality(self) -> None:
        user_id1 = UserId("user-123")
        user_id2 = UserId("user-123")
        assert user_id1 == user_id2

    def test_user_id_inequality(self) -> None:
        user_id1 = UserId("user-123")
        user_id2 = UserId("user-456")
        assert user_id1 != user_id2

    def test_empty_user_id_raises_error(self) -> None:
        with pytest.raises(ValueError, match="UserId cannot be empty"):
            UserId("")

    def test_whitespace_only_user_id_raises_error(self) -> None:
        with pytest.raises(ValueError, match="UserId cannot be empty"):
            UserId("   ")


class TestSessionId:
    """Tests for SessionId value object."""

    def test_create_valid_session_id(self) -> None:
        session_id = SessionId("session-abc")
        assert session_id.value == "session-abc"

    def test_session_id_equality(self) -> None:
        session_id1 = SessionId("session-abc")
        session_id2 = SessionId("session-abc")
        assert session_id1 == session_id2

    def test_empty_session_id_raises_error(self) -> None:
        with pytest.raises(ValueError, match="SessionId cannot be empty"):
            SessionId("")


class TestTurnIndex:
    """Tests for TurnIndex value object.

    Business rule: TurnIndex must be >= 1 (turn indices start from 1)
    """

    def test_create_valid_turn_index(self) -> None:
        turn_index = TurnIndex(1)
        assert turn_index.value == 1

    def test_turn_index_equality(self) -> None:
        turn_index1 = TurnIndex(5)
        turn_index2 = TurnIndex(5)
        assert turn_index1 == turn_index2

    def test_turn_index_zero_raises_error(self) -> None:
        with pytest.raises(ValueError, match="TurnIndex must be >= 1"):
            TurnIndex(0)

    def test_turn_index_negative_raises_error(self) -> None:
        with pytest.raises(ValueError, match="TurnIndex must be >= 1"):
            TurnIndex(-1)

    def test_turn_index_comparison(self) -> None:
        turn1 = TurnIndex(3)
        turn2 = TurnIndex(5)
        assert turn1.value < turn2.value
        assert turn2.value > turn1.value


class TestMessageRole:
    """Tests for MessageRole value object.

    Allowed roles: "user" and "assistant"
    """

    def test_create_user_role(self) -> None:
        role = MessageRole.USER
        assert role.value == "user"

    def test_create_assistant_role(self) -> None:
        role = MessageRole.ASSISTANT
        assert role.value == "assistant"

    def test_role_from_string_user(self) -> None:
        role = MessageRole.from_string("user")
        assert role == MessageRole.USER

    def test_role_from_string_assistant(self) -> None:
        role = MessageRole.from_string("assistant")
        assert role == MessageRole.ASSISTANT

    def test_invalid_role_raises_error(self) -> None:
        with pytest.raises(ValueError, match="Invalid message role"):
            MessageRole.from_string("system")
