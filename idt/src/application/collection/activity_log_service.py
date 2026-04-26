from sqlalchemy.exc import ProgrammingError

from src.domain.collection.interfaces import ActivityLogRepositoryInterface
from src.domain.collection.schemas import ActionType, ActivityLogEntry
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ActivityLogService:
    def __init__(
        self,
        repository: ActivityLogRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repo = repository
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
            await self._repo.save(
                collection_name=collection_name,
                action=action,
                user_id=user_id,
                detail=detail,
                request_id=request_id,
            )
        except Exception as e:
            self._logger.warning(
                "Failed to log activity",
                exception=e,
                collection=collection_name,
                action=action.value,
            )

    async def get_logs(
        self, request_id: str, **filters
    ) -> tuple[list[ActivityLogEntry], int]:
        try:
            logs = await self._repo.find_all(request_id=request_id, **filters)
            count_filters = {
                k: v for k, v in filters.items() if k not in ("limit", "offset")
            }
            total = await self._repo.count(request_id=request_id, **count_filters)
            return logs, total
        except ProgrammingError as e:
            self._logger.warning(
                "Activity log table not available",
                exception=e,
            )
            return [], 0

    async def get_collection_logs(
        self,
        collection_name: str,
        request_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[ActivityLogEntry], int]:
        try:
            logs = await self._repo.find_by_collection(
                collection_name=collection_name,
                request_id=request_id,
                limit=limit,
                offset=offset,
            )
            total = await self._repo.count(
                request_id=request_id,
                collection_name=collection_name,
            )
            return logs, total
        except ProgrammingError as e:
            self._logger.warning(
                "Activity log table not available",
                exception=e,
                collection=collection_name,
            )
            return [], 0
