"""MCP Tool UseCase.

MCP 서버 Tool 목록을 Agent에 제공하는 유스케이스.
application 레이어 — domain 규칙 조합만 담당.
"""

from langchain_core.tools import BaseTool

from src.domain.mcp.value_objects import MCPServerConfig
from src.infrastructure.logging import get_logger
from src.infrastructure.mcp.tool_registry import MCPToolRegistry

logger = get_logger(__name__)


class MCPToolUseCase:
    """LangGraph Agent에 MCP Tool 목록을 제공하는 유스케이스.

    여러 MCP 서버 설정을 받아 Tool Registry를 구성하고,
    요청 시 Agent에서 사용할 수 있는 LangChain Tool 목록을 반환한다.
    """

    def __init__(self, configs: list[MCPServerConfig]) -> None:
        """초기화.

        Args:
            configs: MCP 서버 설정 목록

        Raises:
            ValueError: 서버 수가 정책 상한을 초과하는 경우
        """
        self._registry = MCPToolRegistry(configs)

    async def get_tools_for_agent(self, request_id: str) -> list[BaseTool]:
        """LangGraph Agent에서 사용할 MCP Tool 목록을 반환한다.

        Args:
            request_id: 요청 추적 ID (LOG-001 준수)

        Returns:
            LangChain BaseTool 목록
        """
        logger.info(
            "Loading MCP tools for agent",
            request_id=request_id,
        )
        return await self._registry.get_tools(request_id)
