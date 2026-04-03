"""DeleteMCPServerUseCase: MCP 서버 삭제."""
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface


class DeleteMCPServerUseCase:

    def __init__(
        self,
        repository: MCPServerRegistryRepositoryInterface,
        logger: LoggerInterface,
    ):
        self._repo = repository
        self._logger = logger

    async def execute(self, id: str, request_id: str) -> bool:
        self._logger.info(
            "DeleteMCPServerUseCase start", request_id=request_id, id=id
        )
        result = await self._repo.delete(id, request_id)
        self._logger.info(
            "DeleteMCPServerUseCase done",
            request_id=request_id,
            id=id,
            deleted=result,
        )
        return result
