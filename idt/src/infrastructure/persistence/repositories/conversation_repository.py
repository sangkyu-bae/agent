"""SQLAlchemy implementation of ConversationMessageRepository."""
from typing import List, Optional

from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.repositories.conversation_repository import (
    ConversationMessageRepository,
)
from src.domain.conversation.entities import ConversationMessage, MessageId
from src.domain.conversation.history_schemas import SessionSummary
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
        await self._session.commit()
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

    async def find_sessions_by_user(
        self, user_id: UserId
    ) -> List[SessionSummary]:
        """Return session summaries for a user, newest-first.

        Strategy (design.md §2-3):
          1. GROUP BY session_id → message_count + last_message_at
          2. 각 session_id 의 마지막 user 메시지 내용을 IN 쿼리로 조회
          3. Python-side에서 병합하여 SessionSummary 생성 (truncate 포함)
        """
        agg_stmt = (
            select(
                ConversationMessageModel.session_id.label("session_id"),
                func.count().label("message_count"),
                func.max(ConversationMessageModel.created_at).label(
                    "last_message_at"
                ),
            )
            .where(ConversationMessageModel.user_id == user_id.value)
            .group_by(ConversationMessageModel.session_id)
            .order_by(desc("last_message_at"))
        )
        agg_result = await self._session.execute(agg_stmt)
        agg_rows = agg_result.all()
        if not agg_rows:
            return []

        session_ids = [row.session_id for row in agg_rows]

        last_user_stmt = (
            select(
                ConversationMessageModel.session_id,
                ConversationMessageModel.content,
                ConversationMessageModel.created_at,
            )
            .where(ConversationMessageModel.user_id == user_id.value)
            .where(ConversationMessageModel.session_id.in_(session_ids))
            .where(ConversationMessageModel.role == "user")
            .order_by(
                ConversationMessageModel.session_id,
                desc(ConversationMessageModel.created_at),
            )
        )
        last_user_result = await self._session.execute(last_user_stmt)
        last_user_by_session: dict[str, str] = {}
        for row in last_user_result.all():
            # 정렬상 첫 번째 행이 session 별 가장 최신 user 메시지
            if row.session_id not in last_user_by_session:
                last_user_by_session[row.session_id] = row.content

        return [
            SessionSummary.from_raw(
                session_id=row.session_id,
                message_count=row.message_count,
                last_message=last_user_by_session.get(row.session_id, ""),
                last_message_at=row.last_message_at,
            )
            for row in agg_rows
        ]

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
