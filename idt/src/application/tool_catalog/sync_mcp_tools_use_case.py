"""SyncMcpToolsUseCase: MCP 서버 도구를 tool_catalog에 동기화."""
import uuid

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.tool_catalog.entity import ToolCatalogEntry
from src.domain.tool_catalog.interfaces import ToolCatalogRepositoryInterface


class SyncMcpToolsUseCase:
    def __init__(
        self,
        tool_catalog_repo: ToolCatalogRepositoryInterface,
        mcp_server_repo,
        mcp_tool_loader,
        logger: LoggerInterface,
    ) -> None:
        self._tool_catalog_repo = tool_catalog_repo
        self._mcp_server_repo = mcp_server_repo
        self._mcp_tool_loader = mcp_tool_loader
        self._logger = logger

    async def execute(
        self, mcp_server_id: str | None, request_id: str
    ) -> int:
        self._logger.info("SyncMcpToolsUseCase start", request_id=request_id)
        try:
            if mcp_server_id:
                servers = [await self._mcp_server_repo.find_by_id(mcp_server_id)]
            else:
                servers = await self._mcp_server_repo.find_active_all(request_id)

            count = 0
            for server in servers:
                if server is None:
                    continue
                if not server.is_active:
                    await self._tool_catalog_repo.deactivate_by_mcp_server(
                        server.id, request_id
                    )
                    continue

                tools = await self._mcp_tool_loader.list_tools(server)
                for tool in tools:
                    entry = ToolCatalogEntry(
                        id=str(uuid.uuid4()),
                        tool_id=f"mcp:{server.id}:{tool.name}",
                        source="mcp",
                        mcp_server_id=server.id,
                        name=tool.name,
                        description=tool.description or "",
                        is_active=True,
                    )
                    await self._tool_catalog_repo.upsert_by_tool_id(entry, request_id)
                    count += 1

            self._logger.info(
                "SyncMcpToolsUseCase done",
                request_id=request_id, synced_count=count,
            )
            return count
        except Exception as e:
            self._logger.error(
                "SyncMcpToolsUseCase failed", exception=e, request_id=request_id
            )
            raise
