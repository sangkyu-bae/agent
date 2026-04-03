"""Tests for conversation domain policies.

TDD: These tests are written first before implementation.

Business rules from CLAUDE.md Section 7.3:
- When a session exceeds 6 turns, summarization MUST be performed
- Summary covers turn_index 1 to N-3 (keep last 3 turns)
- Next query uses: summary + last 3 turns as context
"""
from datetime import datetime

import pytest

from src.domain.conversation.policies import SummarizationPolicy
from src.domain.conversation.entities import ConversationMessage, MessageId
from src.domain.conversation.value_objects import (
    UserId,
    SessionId,
    TurnIndex,
    MessageRole,
)


def create_message(turn: int, role: MessageRole = MessageRole.USER) -> ConversationMessage:
    """Helper to create test messages."""
    return ConversationMessage(
        id=MessageId(turn),
        user_id=UserId("user-123"),
        session_id=SessionId("session-abc"),
        role=role,
        content=f"Message at turn {turn}",
        turn_index=TurnIndex(turn),
        created_at=datetime.now(),
    )


class TestSummarizationPolicy:
    """Tests for SummarizationPolicy.

    Key business rules:
    - Summarization threshold: 6 turns
    - Keep last 3 turns in context
    - Summarize turns 1 to N-3
    """

    def test_summarization_not_needed_with_6_or_fewer_turns(self) -> None:
        """No summarization needed when turns <= 6."""
        policy = SummarizationPolicy()
        messages = [create_message(i) for i in range(1, 7)]  # 6 messages

        assert policy.needs_summarization(messages) is False

    def test_summarization_needed_when_exceeds_6_turns(self) -> None:
        """Summarization needed when turns > 6."""
        policy = SummarizationPolicy()
        messages = [create_message(i) for i in range(1, 8)]  # 7 messages

        assert policy.needs_summarization(messages) is True

    def test_summarization_needed_with_10_turns(self) -> None:
        """Summarization needed for 10 turns."""
        policy = SummarizationPolicy()
        messages = [create_message(i) for i in range(1, 11)]  # 10 messages

        assert policy.needs_summarization(messages) is True

    def test_get_turns_to_summarize_returns_all_but_last_3(self) -> None:
        """Should return turns 1 to N-3 for summarization."""
        policy = SummarizationPolicy()
        messages = [create_message(i) for i in range(1, 8)]  # 7 messages

        to_summarize = policy.get_turns_to_summarize(messages)

        # Should return turns 1-4 (7 - 3 = 4)
        assert len(to_summarize) == 4
        assert [m.turn_index.value for m in to_summarize] == [1, 2, 3, 4]

    def test_get_turns_to_summarize_with_10_messages(self) -> None:
        """With 10 messages, should summarize turns 1-7."""
        policy = SummarizationPolicy()
        messages = [create_message(i) for i in range(1, 11)]  # 10 messages

        to_summarize = policy.get_turns_to_summarize(messages)

        # Should return turns 1-7 (10 - 3 = 7)
        assert len(to_summarize) == 7
        assert [m.turn_index.value for m in to_summarize] == [1, 2, 3, 4, 5, 6, 7]

    def test_get_recent_turns_returns_last_3(self) -> None:
        """Should return last 3 turns for context."""
        policy = SummarizationPolicy()
        messages = [create_message(i) for i in range(1, 8)]  # 7 messages

        recent = policy.get_recent_turns(messages)

        # Should return turns 5, 6, 7
        assert len(recent) == 3
        assert [m.turn_index.value for m in recent] == [5, 6, 7]

    def test_get_recent_turns_with_fewer_than_3_messages(self) -> None:
        """With fewer than 3 messages, return all."""
        policy = SummarizationPolicy()
        messages = [create_message(i) for i in range(1, 3)]  # 2 messages

        recent = policy.get_recent_turns(messages)

        assert len(recent) == 2
        assert [m.turn_index.value for m in recent] == [1, 2]

    def test_summarization_threshold_is_configurable(self) -> None:
        """Threshold can be configured via constructor."""
        policy = SummarizationPolicy(threshold=4, keep_recent=2)
        messages = [create_message(i) for i in range(1, 6)]  # 5 messages

        assert policy.needs_summarization(messages) is True

        to_summarize = policy.get_turns_to_summarize(messages)
        # Should summarize turns 1-3 (5 - 2 = 3)
        assert len(to_summarize) == 3

        recent = policy.get_recent_turns(messages)
        # Should keep last 2
        assert len(recent) == 2

    def test_empty_message_list(self) -> None:
        """Empty message list needs no summarization."""
        policy = SummarizationPolicy()

        assert policy.needs_summarization([]) is False
        assert policy.get_turns_to_summarize([]) == []
        assert policy.get_recent_turns([]) == []

    def test_messages_sorted_by_turn_index(self) -> None:
        """Policy should handle unsorted messages correctly."""
        policy = SummarizationPolicy()
        # Create messages out of order
        messages = [
            create_message(5),
            create_message(2),
            create_message(7),
            create_message(1),
            create_message(4),
            create_message(3),
            create_message(6),
        ]

        to_summarize = policy.get_turns_to_summarize(messages)
        recent = policy.get_recent_turns(messages)

        # Should be correctly sorted
        assert [m.turn_index.value for m in to_summarize] == [1, 2, 3, 4]
        assert [m.turn_index.value for m in recent] == [5, 6, 7]

    def test_get_summary_range(self) -> None:
        """Should return the turn range that was summarized."""
        policy = SummarizationPolicy()
        messages = [create_message(i) for i in range(1, 8)]  # 7 messages

        start_turn, end_turn = policy.get_summary_range(messages)

        assert start_turn.value == 1
        assert end_turn.value == 4

    def test_get_summary_range_raises_when_not_needed(self) -> None:
        """Should raise error when summarization not needed."""
        policy = SummarizationPolicy()
        messages = [create_message(i) for i in range(1, 5)]  # 4 messages

        with pytest.raises(ValueError, match="Summarization not needed"):
            policy.get_summary_range(messages)
