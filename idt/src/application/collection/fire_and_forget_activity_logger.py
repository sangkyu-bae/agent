"""Fire-and-forget activity logger for cross-cutting concerns.

Used by singleton UseCases (e.g. RetrievalUseCase) that cannot receive
per-request DB sessions via Depends. Manages its own session lifecycle
and never propagates exceptions to callers.
"""
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from src.domain.collection.schemas import ActionType
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.collection.activity_log_repository import ActivityLogRepository


class FireAndForgetActivityLogger:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        logger: LoggerInterface,
    ) -> None:
        self._session_factory = session_factory
        self._logger = logger

    async def log(
        self,
        collection_name: str,
        action: ActionType,
        request_id: str,
        user_id: str | None = None,
        detail: dict | None = None,
    ) -> None:
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    repo = ActivityLogRepository(session, self._logger)
                    await repo.save(
                        collection_name=collection_name,
                        action=action,
                        user_id=user_id,
                        detail=detail,
                        request_id=request_id,
                    )
        except Exception as e:
            self._logger.warning(
                "Fire-and-forget activity log failed",
                exception=e,
                collection=collection_name,
                action=action.value,
            )
