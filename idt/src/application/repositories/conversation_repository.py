"""Abstract repository interface for conversation messages."""
from abc import ABC, abstractmethod
from typing import List, Optional

from src.domain.conversation.entities import ConversationMessage, MessageId
from src.domain.conversation.history_schemas import SessionSummary
from src.domain.conversation.value_objects import UserId, SessionId


class ConversationMessageRepository(ABC):
    """Abstract repository for conversation message operations.

    Implementations must be provided by the infrastructure layer.
    """

    @abstractmethod
    async def save(self, message: ConversationMessage) -> ConversationMessage:
        """Save a conversation message.

        Args:
            message: The message to save

        Returns:
            The saved message with its assigned ID
        """
        pass

    @abstractmethod
    async def find_by_id(self, message_id: MessageId) -> Optional[ConversationMessage]:
        """Find a message by its ID.

        Args:
            message_id: The message ID to search for

        Returns:
            The message if found, None otherwise
        """
        pass

    @abstractmethod
    async def find_by_session(
        self, user_id: UserId, session_id: SessionId
    ) -> List[ConversationMessage]:
        """Find all messages in a session.

        Args:
            user_id: The user ID
            session_id: The session ID

        Returns:
            List of messages sorted by turn_index
        """
        pass

    @abstractmethod
    async def get_message_count(
        self, user_id: UserId, session_id: SessionId
    ) -> int:
        """Get the number of messages in a session.

        Args:
            user_id: The user ID
            session_id: The session ID

        Returns:
            Number of messages in the session
        """
        pass

    @abstractmethod
    async def find_sessions_by_user(
        self, user_id: UserId
    ) -> List[SessionSummary]:
        """Return session summaries for a user, newest-first.

        Args:
            user_id: The user ID

        Returns:
            List of SessionSummary sorted by last_message_at desc.
        """
        pass

    @abstractmethod
    async def delete_by_session(
        self, user_id: UserId, session_id: SessionId
    ) -> int:
        """Delete all messages in a session.

        Args:
            user_id: The user ID
            session_id: The session ID

        Returns:
            Number of messages deleted
        """
        pass
