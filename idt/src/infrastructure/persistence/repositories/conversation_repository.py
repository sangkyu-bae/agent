"""SQLAlchemy implementation of ConversationMessageRepository."""
from typing import List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.repositories.conversation_repository import (
    ConversationMessageRepository,
)
from src.domain.conversation.entities import ConversationMessage, MessageId
from src.domain.conversation.value_objects import SessionId, UserId
from src.infrastructure.persistence.mappers.conversation_mapper import (
    ConversationMessageMapper,
)
from src.infrastructure.persistence.models.conversation import (
    ConversationMessageModel,
)


class SQLAlchemyConversationMessageRepository(ConversationMessageRepository):
    """SQLAlchemy-based implementation of conversation message repository."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session
        """
        self._session = session

    async def save(self, message: ConversationMessage) -> ConversationMessage:
        """Save a conversation message.

        Args:
            message: The message to save

        Returns:
            The saved message with its assigned ID
        """
        model = ConversationMessageMapper.to_model(message)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return ConversationMessageMapper.to_entity(model)

    async def find_by_id(
        self, message_id: MessageId
    ) -> Optional[ConversationMessage]:
        """Find a message by its ID.

        Args:
            message_id: The message ID to search for

        Returns:
            The message if found, None otherwise
        """
        stmt = select(ConversationMessageModel).where(
            ConversationMessageModel.id == message_id.value
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return ConversationMessageMapper.to_entity(model) if model else None

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
        stmt = (
            select(ConversationMessageModel)
            .where(ConversationMessageModel.user_id == user_id.value)
            .where(ConversationMessageModel.session_id == session_id.value)
            .order_by(ConversationMessageModel.turn_index)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [ConversationMessageMapper.to_entity(m) for m in models]

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
        stmt = (
            select(func.count())
            .select_from(ConversationMessageModel)
            .where(ConversationMessageModel.user_id == user_id.value)
            .where(ConversationMessageModel.session_id == session_id.value)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

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
        stmt = (
            delete(ConversationMessageModel)
            .where(ConversationMessageModel.user_id == user_id.value)
            .where(ConversationMessageModel.session_id == session_id.value)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount
