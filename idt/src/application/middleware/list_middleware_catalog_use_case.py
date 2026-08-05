"""ListMiddlewareCatalogUseCase: 카탈로그 목록 (폼·관리자 화면 공용)."""
from src.application.middleware.schemas import (
    MiddlewareCatalogItemResponse,
    MiddlewareCatalogListResponse,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.middleware.interfaces import MiddlewareCatalogRepositoryInterface


class ListMiddlewareCatalogUseCase:
    def __init__(
        self,
        repository: MiddlewareCatalogRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(self, request_id: str) -> MiddlewareCatalogListResponse:
        try:
            entries = await self._repository.list_all(request_id)
            return MiddlewareCatalogListResponse(
                middlewares=[
                    MiddlewareCatalogItemResponse.from_entity(e) for e in entries
                ]
            )
        except Exception as e:
            self._logger.error(
                "ListMiddlewareCatalogUseCase failed",
                exception=e,
                request_id=request_id,
            )
            raise
