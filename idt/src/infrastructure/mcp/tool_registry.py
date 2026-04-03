"""MCP Tool Registry.

여러 MCP 서버에 연결하여 Tool 목록을 자동 발견하고
LangChain BaseTool 목록으로 반환한다.
infrastructure 레이어 — 비즈니스 규칙 없음.
"""

from langchain_core.tools import BaseTool

from src.domain.mcp.policy import MCPConnectionPolicy
from src.domain.mcp.value_objects import MCPServerConfig
from src.infrastructure.logging import get_logger
from src.infrastructure.mcp.client_factory import MCPClientFactory
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter

logger = get_logger(__name__)


class MCPToolRegistry:
    """MCP 서버 Tool 레지스트리.

    등록된 MCP 서버들에서 Tool 목록을 자동 발견하고
    LangChain BaseTool 리스트로 반환한다.
    단일 서버 연결 실패 시 해당 서버를 건너뛰고 나머지를 계속 처리한다.
    """

    def __init__(self, configs: list[MCPServerConfig]) -> None:
        """초기화.

        Args:
            configs: MCP 서버 설정 목록

        Raises:
            ValueError: 서버 수가 정책 상한을 초과하는 경우
        """
        if not MCPConnectionPolicy.validate_server_count(len(configs)):
            raise ValueError(
                f"Too many MCP servers: {len(configs)} > {MCPConnectionPolicy.MAX_SERVERS}"
            )
        self._configs = configs

    async def get_tools(self, request_id: str | None = None) -> list[BaseTool]:
        """모든 등록된 MCP 서버의 Tool 목록을 LangChain Tool로 반환한다.

        단일 서버 연결 실패는 경고 로그를 남기고 빈 리스트로 처리한다
        (전체 실패 방지).

        Args:
            request_id: 요청 추적 ID

        Returns:
            LangChain BaseTool 목록
        """
        all_tools: list[BaseTool] = []

        for config in self._configs:
            tools = await self._load_server_tools(config, request_id)
            all_tools.extend(tools)

        logger.info(
            "MCP tools loaded",
            request_id=request_id,
            server_count=len(self._configs),
            total_tools=len(all_tools),
        )

        return all_tools

    async def _load_server_tools(
        self,
        config: MCPServerConfig,
        request_id: str | None,
    ) -> list[BaseTool]:
        """단일 MCP 서버에서 Tool 목록을 로드한다."""
        log_extra = {"request_id": request_id, "server": config.name}

        try:
            async with MCPClientFactory.create_session(config, request_id) as session:
                tools_response = await session.list_tools()

            tools: list[BaseTool] = []
            for mcp_tool in tools_response.tools:
                tool_name = MCPConnectionPolicy.sanitize_tool_name(
                    f"{config.name}_{mcp_tool.name}"
                )
                adapter = MCPToolAdapter(
                    name=tool_name,
                    description=mcp_tool.description or f"MCP tool: {mcp_tool.name}",
                    server_config=config,
                    mcp_tool_name=mcp_tool.name,
                )
                tools.append(adapter)

            logger.info(
                "MCP server tools loaded",
                tool_count=len(tools),
                **log_extra,
            )
            return tools

        except Exception as e:
            logger.error(
                "Failed to load MCP server tools",
                exception=e,
                **log_extra,
            )
            return []
