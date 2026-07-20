"""admin-dashboard 유스케이스 4종 (Design D3).

읽기 집계 위임 + 구조화 로깅 — 비즈니스 규칙 없음 (각 유스케이스는 위임 1회).
"""
from src.domain.admin_dashboard.interfaces import (
    DashboardAggregationRepositoryInterface,
    StorageHealthPort,
)
from src.domain.admin_dashboard.schemas import (
    DashboardStats,
    HealthComponent,
    KbBreakdownRow,
    RecentDocumentRow,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class GetDashboardStatsUseCase:
    def __init__(
        self,
        repo: DashboardAggregationRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repo = repo
        self._logger = logger

    async def execute(self, request_id: str) -> DashboardStats:
        self._logger.info("dashboard stats started", request_id=request_id)
        try:
            stats = await self._repo.get_stats()
        except Exception as e:
            self._logger.error(
                "dashboard stats failed", exception=e, request_id=request_id
            )
            raise
        self._logger.info(
            "dashboard stats completed",
            request_id=request_id,
            kb_total=stats.kb.total,
            document_total=stats.documents.total,
        )
        return stats


class GetKbBreakdownUseCase:
    def __init__(
        self,
        repo: DashboardAggregationRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repo = repo
        self._logger = logger

    async def execute(self, request_id: str) -> list[KbBreakdownRow]:
        self._logger.info("kb breakdown started", request_id=request_id)
        try:
            rows = await self._repo.get_kb_breakdown()
        except Exception as e:
            self._logger.error(
                "kb breakdown failed", exception=e, request_id=request_id
            )
            raise
        self._logger.info(
            "kb breakdown completed", request_id=request_id, row_count=len(rows)
        )
        return rows


class GetRecentDocumentsUseCase:
    def __init__(
        self,
        repo: DashboardAggregationRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repo = repo
        self._logger = logger

    async def execute(self, limit: int, request_id: str) -> list[RecentDocumentRow]:
        self._logger.info(
            "recent documents started", request_id=request_id, limit=limit
        )
        try:
            rows = await self._repo.get_recent_documents(limit=limit)
        except Exception as e:
            self._logger.error(
                "recent documents failed", exception=e, request_id=request_id
            )
            raise
        self._logger.info(
            "recent documents completed", request_id=request_id, row_count=len(rows)
        )
        return rows


class StorageHealthCheckUseCase:
    def __init__(self, port: StorageHealthPort, logger: LoggerInterface) -> None:
        self._port = port
        self._logger = logger

    async def execute(self, request_id: str) -> list[HealthComponent]:
        components = await self._port.check_all()
        failed = [c.name for c in components if c.status != "ok"]
        if failed:
            self._logger.warning(
                "storage health degraded", request_id=request_id, failed=failed
            )
        else:
            self._logger.info("storage health ok", request_id=request_id)
        return components
