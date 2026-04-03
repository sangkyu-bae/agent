"""LoadMCPToolsUseCase: DB 등록 MCP 서버 → LangChain BaseTool 변환."""
from langchain_core.tools import BaseTool

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.mcp_registry.schemas import MCPServerRegistration


class LoadMCPToolsUseCase:
    """
    DB에 등록된 활성 MCP 서버들을 LangChain BaseTool 목록으로 반환.
    하나의 서버 연결 실패는 전체를 중단시키지 않는다 (부분 실패 허용).
    """

    def __init__(
        self,
        repository: MCPServerRegistryRepositoryInterface,
        mcp_tool_loader,
        logger: LoggerInterface,
    ):
        self._repo = repository
        self._loader = mcp_tool_loader
        self._logger = logger

    async def execute(self, request_id: str) -> list[BaseTool]:
        """활성 MCP 서버에서 LangChain BaseTool 목록 반환."""
        self._logger.info("LoadMCPToolsUseCase start", request_id=request_id)

        registrations = await self._repo.find_all_active(request_id)
        tools: list[BaseTool] = []

        for reg in registrations:
            try:
                loaded = await self._loader.load(reg, request_id)
                tools.extend(loaded)
            except Exception as e:
                self._logger.error(
                    "MCP server load failed, skipping",
                    request_id=request_id,
                    server_id=reg.id,
                    server_name=reg.name,
                    exception=e,
                )

        self._logger.info(
            "LoadMCPToolsUseCase done",
            request_id=request_id,
            total_tools=len(tools),
        )
        return tools

    async def list_meta(
        self, request_id: str
    ) -> list[MCPServerRegistration]:
        """DB에서 활성 MCP 서버 메타 목록만 반환 (연결 없음)."""
        return await self._repo.find_all_active(request_id)
