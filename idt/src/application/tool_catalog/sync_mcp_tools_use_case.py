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
                servers = [
                    await self._mcp_server_repo.find_by_id(mcp_server_id, request_id)
                ]
            else:
                servers = await self._mcp_server_repo.find_all_active(request_id)

            count = 0
            for server in servers:
                if server is None:
                    continue
                if not server.is_active:
                    await self._tool_catalog_repo.deactivate_by_mcp_server(
                        server.id, request_id
                    )
                    continue

                tools = await self._mcp_tool_loader.load(server, request_id)
                for tool in tools:
                    # 어댑터의 .name은 'mcp_{uuid}_{tool}'로 접두사가 붙는다.
                    # 카탈로그 계약은 원본 이름 기준이다 — mcp:{server_id}:{tool}.
                    tool_name = tool.mcp_tool_name
                    # Design Ref: mcp-tool-category-routing §5 D-02 (FR-03) —
                    # category / max_tool_calls는 관리자 지정값이다. sync가
                    # 만드는 entry는 이 값을 참칭하지 않고 기본(None)으로 둔다.
                    # 실제 보존은 repository UPDATE 분기가 두 컬럼을 SET 절에
                    # 넣지 않음으로써 성립한다 (is_builtin D2와 동형).
                    entry = ToolCatalogEntry(
                        id=str(uuid.uuid4()),
                        tool_id=f"mcp:{server.id}:{tool_name}",
                        source="mcp",
                        mcp_server_id=server.id,
                        name=tool_name,
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
