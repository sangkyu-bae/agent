from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.collection.interfaces import ActivityLogRepositoryInterface
from src.domain.collection.schemas import ActionType, ActivityLogEntry
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.collection.models import CollectionActivityLogModel


class ActivityLogRepository(ActivityLogRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(
        self,
        collection_name: str,
        action: ActionType,
        user_id: str | None,
        detail: dict | None,
        request_id: str,
    ) -> None:
        log = CollectionActivityLogModel(
            collection_name=collection_name,
            action=action.value,
            user_id=user_id,
            detail=detail,
        )
        self._session.add(log)
        await self._session.flush()

    async def find_by_collection(
        self,
        collection_name: str,
        request_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActivityLogEntry]:
        stmt = (
            select(CollectionActivityLogModel)
            .where(CollectionActivityLogModel.collection_name == collection_name)
            .order_by(CollectionActivityLogModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return [self._to_entry(row) for row in result.scalars().all()]

    async def find_all(
        self,
        request_id: str,
        collection_name: str | None = None,
        action: str | None = None,
        user_id: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActivityLogEntry]:
        stmt = select(CollectionActivityLogModel)
        stmt = self._apply_filters(
            stmt, collection_name, action, user_id, from_date, to_date
        )
        stmt = (
            stmt.order_by(CollectionActivityLogModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return [self._to_entry(row) for row in result.scalars().all()]

    async def count(
        self,
        request_id: str,
        collection_name: str | None = None,
        action: str | None = None,
        user_id: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(CollectionActivityLogModel)
        stmt = self._apply_filters(
            stmt, collection_name, action, user_id, from_date, to_date
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    @staticmethod
    def _apply_filters(stmt, collection_name, action, user_id, from_date, to_date):
        if collection_name:
            stmt = stmt.where(
                CollectionActivityLogModel.collection_name == collection_name
            )
        if action:
            stmt = stmt.where(CollectionActivityLogModel.action == action)
        if user_id:
            stmt = stmt.where(CollectionActivityLogModel.user_id == user_id)
        if from_date:
            stmt = stmt.where(CollectionActivityLogModel.created_at >= from_date)
        if to_date:
            stmt = stmt.where(CollectionActivityLogModel.created_at <= to_date)
        return stmt

    @staticmethod
    def _to_entry(model: CollectionActivityLogModel) -> ActivityLogEntry:
        return ActivityLogEntry(
            id=model.id,
            collection_name=model.collection_name,
            action=ActionType(model.action),
            user_id=model.user_id,
            detail=model.detail,
            created_at=model.created_at,
        )
