"""MCP Tool Adapter.

MCP 서버의 개별 Tool을 LangChain BaseTool로 래핑한다.
infrastructure 레이어 — 비즈니스 규칙 없음.
"""

from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.domain.mcp.value_objects import MCPServerConfig
from src.infrastructure.logging import get_logger
from src.infrastructure.mcp.client_factory import MCPClientFactory

logger = get_logger(__name__)


class MCPToolInput(BaseModel):
    """MCP Tool 공통 입력 스키마."""

    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool 실행 인수 (MCP tool schema에 따라 다름)",
    )


class MCPToolAdapter(BaseTool):
    """MCP Tool → LangChain BaseTool 어댑터.

    하나의 MCP Tool을 하나의 LangChain Tool로 표현한다.
    LangGraph Agent에서 투명하게 사용할 수 있다.
    """

    name: str
    description: str
    args_schema: type[BaseModel] = MCPToolInput

    server_config: MCPServerConfig
    mcp_tool_name: str

    model_config = {"arbitrary_types_allowed": True}

    def _run(self, arguments: dict[str, Any] | None = None) -> str:
        """동기 실행 — 이벤트 루프를 통해 비동기 위임."""
        import asyncio

        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self._arun(arguments=arguments or {}))

    async def _arun(self, arguments: dict[str, Any] | None = None) -> str:
        """MCP Tool 비동기 실행.

        Args:
            arguments: Tool 실행 인수

        Returns:
            실행 결과 텍스트 (content 항목들을 줄바꿈으로 연결)

        Raises:
            연결 실패 또는 Tool 실행 오류 시 예외 전파
        """
        args = arguments or {}
        log_extra = {
            "server": self.server_config.name,
            "tool": self.mcp_tool_name,
        }

        logger.info("MCP tool execution started", **log_extra)

        try:
            async with MCPClientFactory.create_session(self.server_config) as session:
                result = await session.call_tool(
                    name=self.mcp_tool_name,
                    arguments=args,
                )

            content = MCPToolAdapter._extract_content(result)
            logger.info("MCP tool execution completed", **log_extra)
            return content

        except Exception as e:
            logger.error(
                "MCP tool execution failed",
                exception=e,
                **log_extra,
            )
            raise

    @staticmethod
    def _extract_content(result: Any) -> str:
        """MCP 실행 결과에서 텍스트 콘텐츠를 추출한다.

        Args:
            result: MCP call_tool 반환값

        Returns:
            결합된 텍스트 문자열
        """
        if hasattr(result, "content") and result.content:
            parts = []
            for item in result.content:
                if hasattr(item, "text"):
                    parts.append(item.text)
                elif hasattr(item, "data"):
                    parts.append(str(item.data))
            return "\n".join(parts)
        return ""
