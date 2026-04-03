"""SQLAlchemy implementation of ConversationSummaryRepository."""
from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.repositories.conversation_summary_repository import (
    ConversationSummaryRepository,
)
from src.domain.conversation.entities import ConversationSummary, SummaryId
from src.domain.conversation.value_objects import SessionId, UserId
from src.infrastructure.persistence.mappers.conversation_mapper import (
    ConversationSummaryMapper,
)
from src.infrastructure.persistence.models.conversation import (
    ConversationSummaryModel,
)


class SQLAlchemyConversationSummaryRepository(ConversationSummaryRepository):
    """SQLAlchemy-based implementation of conversation summary repository."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session
        """
        self._session = session

    async def save(self, summary: ConversationSummary) -> ConversationSummary:
        """Save a conversation summary.

        Args:
            summary: The summary to save

        Returns:
            The saved summary with its assigned ID
        """
        model = ConversationSummaryMapper.to_model(summary)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return ConversationSummaryMapper.to_entity(model)

    async def find_by_id(
        self, summary_id: SummaryId
    ) -> Optional[ConversationSummary]:
        """Find a summary by its ID.

        Args:
            summary_id: The summary ID to search for

        Returns:
            The summary if found, None otherwise
        """
        stmt = select(ConversationSummaryModel).where(
            ConversationSummaryModel.id == summary_id.value
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return ConversationSummaryMapper.to_entity(model) if model else None

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
        stmt = (
            select(ConversationSummaryModel)
            .where(ConversationSummaryModel.user_id == user_id.value)
            .where(ConversationSummaryModel.session_id == session_id.value)
            .order_by(ConversationSummaryModel.start_turn)
        )
        result = await self._session.execute(stmt)
        models = result.scalars().all()
        return [ConversationSummaryMapper.to_entity(m) for m in models]

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
        stmt = (
            select(ConversationSummaryModel)
            .where(ConversationSummaryModel.user_id == user_id.value)
            .where(ConversationSummaryModel.session_id == session_id.value)
            .order_by(ConversationSummaryModel.end_turn.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return ConversationSummaryMapper.to_entity(model) if model else None

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
        stmt = (
            delete(ConversationSummaryModel)
            .where(ConversationSummaryModel.user_id == user_id.value)
            .where(ConversationSummaryModel.session_id == session_id.value)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount
