"""Abstract repository interface for conversation summaries."""
from abc import ABC, abstractmethod
from typing import List, Optional

from src.domain.conversation.entities import ConversationSummary, SummaryId
from src.domain.conversation.value_objects import UserId, SessionId


class ConversationSummaryRepository(ABC):
    """Abstract repository for conversation summary operations.

    Implementations must be provided by the infrastructure layer.
    """

    @abstractmethod
    async def save(self, summary: ConversationSummary) -> ConversationSummary:
        """Save a conversation summary.

        Args:
            summary: The summary to save

        Returns:
            The saved summary with its assigned ID
        """
        pass

    @abstractmethod
    async def find_by_id(self, summary_id: SummaryId) -> Optional[ConversationSummary]:
        """Find a summary by its ID.

        Args:
            summary_id: The summary ID to search for

        Returns:
            The summary if found, None otherwise
        """
        pass

    @abstractmethod
    async def find_by_session(
        self, user_id: UserId, session_id: SessionId
    ) -> List[ConversationSummary]:
        """Find all summaries for a session.

        Args:
            user_id: The user ID
            session_id: The session ID

        Returns:
            List of summaries sorted by start_turn
        """
        pass

    @abstractmethod
    async def find_latest_by_session(
        self, user_id: UserId, session_id: SessionId
    ) -> Optional[ConversationSummary]:
        """Find the most recent summary for a session.

        Args:
            user_id: The user ID
            session_id: The session ID

        Returns:
            The latest summary if exists, None otherwise
        """
        pass

    @abstractmethod
    async def delete_by_session(
        self, user_id: UserId, session_id: SessionId
    ) -> int:
        """Delete all summaries for a session.

        Args:
            user_id: The user ID
            session_id: The session ID

        Returns:
            Number of summaries deleted
        """
        pass
