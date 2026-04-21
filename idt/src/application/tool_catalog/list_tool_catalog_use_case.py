"""ListToolCatalogUseCase: 활성 도구 카탈로그 목록 조회."""
from src.application.tool_catalog.schemas import ToolCatalogItemResponse, ToolCatalogListResponse
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tool_catalog.interfaces import ToolCatalogRepositoryInterface


class ListToolCatalogUseCase:
    def __init__(
        self,
        repository: ToolCatalogRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(self, request_id: str) -> ToolCatalogListResponse:
        self._logger.info("ListToolCatalogUseCase start", request_id=request_id)
        try:
            entries = await self._repository.list_active(request_id)
            self._logger.info(
                "ListToolCatalogUseCase done",
                request_id=request_id, count=len(entries),
            )
            return ToolCatalogListResponse(
                tools=[
                    ToolCatalogItemResponse(
                        tool_id=e.tool_id,
                        source=e.source,
                        name=e.name,
                        description=e.description,
                        mcp_server_id=e.mcp_server_id,
                        requires_env=e.requires_env,
                    )
                    for e in entries
                ]
            )
        except Exception as e:
            self._logger.error(
                "ListToolCatalogUseCase failed", exception=e, request_id=request_id
            )
            raise
