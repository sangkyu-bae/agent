"""ListMCPServersUseCase: MCP 서버 목록/단건 조회."""
from src.application.mcp_registry.schemas import (
    ListMCPServersResponse,
    MCPServerResponse,
    to_response,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface


class ListMCPServersUseCase:

    def __init__(
        self,
        repository: MCPServerRegistryRepositoryInterface,
        logger: LoggerInterface,
    ):
        self._repo = repository
        self._logger = logger

    async def execute_by_user(
        self, user_id: str, request_id: str
    ) -> ListMCPServersResponse:
        self._logger.info(
            "ListMCPServersUseCase by_user start",
            request_id=request_id,
            user_id=user_id,
        )
        items = await self._repo.find_by_user(user_id, request_id)
        self._logger.info(
            "ListMCPServersUseCase by_user done",
            request_id=request_id,
            count=len(items),
        )
        return ListMCPServersResponse(
            items=[to_response(r) for r in items], total=len(items)
        )

    async def execute_all(self, request_id: str) -> ListMCPServersResponse:
        self._logger.info(
            "ListMCPServersUseCase all start", request_id=request_id
        )
        items = await self._repo.find_all_active(request_id)
        self._logger.info(
            "ListMCPServersUseCase all done",
            request_id=request_id,
            count=len(items),
        )
        return ListMCPServersResponse(
            items=[to_response(r) for r in items], total=len(items)
        )

    async def execute_by_id(
        self, id: str, request_id: str
    ) -> MCPServerResponse | None:
        item = await self._repo.find_by_id(id, request_id)
        return to_response(item) if item else None
