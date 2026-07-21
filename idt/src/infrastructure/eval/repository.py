"""MessageFeedbackRepository — message_feedback CRUD·집계 (agent-eval-gate).

SearchHistoryRepository 경량 패턴: (session, logger), flush까지만.
"""
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.eval.entity import MessageFeedback, Rating
from src.domain.eval.interfaces import MessageFeedbackRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.eval.models import MessageFeedbackModel


class MessageFeedbackRepository(MessageFeedbackRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def find_by_message_and_user(
        self, message_id: int, user_id: str, request_id: str
    ) -> MessageFeedback | None:
        model = await self._get_model(message_id, user_id)
        return self._to_entity(model) if model is not None else None

    async def upsert(
        self, feedback: MessageFeedback, request_id: str
    ) -> MessageFeedback:
        model = await self._get_model(feedback.message_id, feedback.user_id)
        if model is None:
            model = MessageFeedbackModel(
                message_id=feedback.message_id,
                user_id=feedback.user_id,
                agent_id=feedback.agent_id,
                rating=feedback.rating.value,
                comment=feedback.comment,
            )
            self._session.add(model)
        else:
            model.rating = feedback.rating.value
            model.comment = feedback.comment
        await self._session.flush()
        return self._to_entity(model)

    async def delete(self, message_id: int, user_id: str, request_id: str) -> bool:
        model = await self._get_model(message_id, user_id)
        if model is None:
            return False
        await self._session.delete(model)
        await self._session.flush()
        return True

    async def aggregate_by_agent(
        self, request_id: str
    ) -> list[tuple[str, int, int]]:
        up = func.sum(
            case((MessageFeedbackModel.rating == Rating.UP.value, 1), else_=0)
        )
        down = func.sum(
            case((MessageFeedbackModel.rating == Rating.DOWN.value, 1), else_=0)
        )
        stmt = select(MessageFeedbackModel.agent_id, up, down).group_by(
            MessageFeedbackModel.agent_id
        )
        rows = (await self._session.execute(stmt)).all()
        return [(r[0], int(r[1] or 0), int(r[2] or 0)) for r in rows]

    async def recent_negative(
        self, limit: int, request_id: str
    ) -> list[MessageFeedback]:
        stmt = (
            select(MessageFeedbackModel)
            .where(MessageFeedbackModel.rating == Rating.DOWN.value)
            .order_by(MessageFeedbackModel.created_at.desc(), MessageFeedbackModel.id.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._to_entity(r) for r in rows]

    async def _get_model(self, message_id: int, user_id: str):
        stmt = select(MessageFeedbackModel).where(
            MessageFeedbackModel.message_id == message_id,
            MessageFeedbackModel.user_id == user_id,
        )
        return (await self._session.execute(stmt)).scalars().first()

    @staticmethod
    def _to_entity(model: MessageFeedbackModel) -> MessageFeedback:
        return MessageFeedback(
            id=model.id,
            message_id=model.message_id,
            user_id=model.user_id,
            agent_id=model.agent_id,
            rating=Rating(model.rating),
            comment=model.comment,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
