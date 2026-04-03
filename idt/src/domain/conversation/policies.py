"""Domain policies for conversation management.

Business rules from CLAUDE.md Section 7.3:
- When a session exceeds 6 turns, summarization MUST be performed
- Summary covers turn_index 1 to N-3 (keep last 3 turns)
- Next query uses: summary + last 3 turns as context
"""
from typing import List, Tuple

from src.domain.conversation.entities import ConversationMessage
from src.domain.conversation.value_objects import TurnIndex


class SummarizationPolicy:
    """Policy for determining when and how to summarize conversations.

    Default configuration per CLAUDE.md:
    - threshold: 6 turns (summarize when exceeds this)
    - keep_recent: 3 turns (keep last 3 turns in context)
    """

    def __init__(self, threshold: int = 6, keep_recent: int = 3) -> None:
        """Initialize the summarization policy.

        Args:
            threshold: Number of turns before summarization is needed
            keep_recent: Number of recent turns to keep in context
        """
        self._threshold = threshold
        self._keep_recent = keep_recent

    def needs_summarization(self, messages: List[ConversationMessage]) -> bool:
        """Check if conversation needs summarization.

        Args:
            messages: List of conversation messages

        Returns:
            True if message count exceeds threshold
        """
        return len(messages) > self._threshold

    def get_turns_to_summarize(
        self, messages: List[ConversationMessage]
    ) -> List[ConversationMessage]:
        """Get the messages that should be summarized.

        Returns messages from turn 1 to N - keep_recent.

        Args:
            messages: List of conversation messages

        Returns:
            List of messages to be summarized (sorted by turn_index)
        """
        if not messages:
            return []

        sorted_messages = sorted(messages, key=lambda m: m.turn_index.value)
        cut_off = len(sorted_messages) - self._keep_recent

        if cut_off <= 0:
            return []

        return sorted_messages[:cut_off]

    def get_recent_turns(
        self, messages: List[ConversationMessage]
    ) -> List[ConversationMessage]:
        """Get the most recent turns to keep in context.

        Args:
            messages: List of conversation messages

        Returns:
            List of most recent messages (sorted by turn_index)
        """
        if not messages:
            return []

        sorted_messages = sorted(messages, key=lambda m: m.turn_index.value)

        if len(sorted_messages) <= self._keep_recent:
            return sorted_messages

        return sorted_messages[-self._keep_recent :]

    def get_summary_range(
        self, messages: List[ConversationMessage]
    ) -> Tuple[TurnIndex, TurnIndex]:
        """Get the turn range that will be summarized.

        Args:
            messages: List of conversation messages

        Returns:
            Tuple of (start_turn, end_turn) for the summary

        Raises:
            ValueError: If summarization is not needed
        """
        if not self.needs_summarization(messages):
            raise ValueError("Summarization not needed")

        to_summarize = self.get_turns_to_summarize(messages)
        return (to_summarize[0].turn_index, to_summarize[-1].turn_index)
