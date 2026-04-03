"""MCPToolLoader: DB 등록 MCP 서버 → LangChain BaseTool 변환."""
from langchain_core.tools import BaseTool

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mcp_registry.schemas import MCPServerRegistration
from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport, SSEServerConfig
from src.infrastructure.mcp.tool_registry import MCPToolRegistry


class MCPToolLoader:
    """
    MCPServerRegistration → MCPServerConfig(SSE) 조립 후
    MCPToolRegistry(MCP-001)로 LangChain BaseTool 목록 반환.
    """

    def __init__(self, logger: LoggerInterface):
        self._logger = logger

    async def load(
        self,
        registration: MCPServerRegistration,
        request_id: str,
    ) -> list[BaseTool]:
        """단일 MCP 서버 등록 정보 → LangChain BaseTool 목록."""
        self._logger.info(
            "MCPToolLoader load start",
            request_id=request_id,
            server_id=registration.id,
            server_name=registration.name,
        )

        config = MCPServerConfig(
            name=registration.tool_id,  # "mcp_{uuid}"
            transport=MCPTransport.SSE,
            sse=SSEServerConfig(url=registration.endpoint),
        )
        registry = MCPToolRegistry(configs=[config])
        tools = await registry.get_tools(request_id=request_id)

        self._logger.info(
            "MCPToolLoader load done",
            request_id=request_id,
            server_id=registration.id,
            tool_count=len(tools),
        )
        return tools

    async def load_by_tool_id(
        self,
        tool_id: str,
        repository,
        request_id: str,
    ) -> list[BaseTool]:
        """
        tool_id("mcp_{uuid}") → DB 조회 → BaseTool 목록 반환.
        ToolFactory에서 mcp_ 접두사 도구 실행 시 호출.

        Args:
            tool_id: "mcp_{uuid}" 형태의 도구 ID
            repository: MCPServerRegistryRepositoryInterface
            request_id: 요청 추적 ID

        Returns:
            BaseTool 목록 (서버를 찾지 못하면 빈 리스트)
        """
        # "mcp_" 접두사 제거 → DB PK
        raw_id = tool_id.removeprefix("mcp_")
        registration = await repository.find_by_id(raw_id, request_id)

        if registration is None:
            self._logger.error(
                "MCPToolLoader load_by_tool_id: registration not found",
                request_id=request_id,
                tool_id=tool_id,
            )
            return []

        return await self.load(registration, request_id)
