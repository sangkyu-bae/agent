"""MCP Tool Adapter.

MCP 서버의 개별 Tool을 LangChain BaseTool로 래핑한다.
infrastructure 레이어 — 비즈니스 규칙 없음.
"""

from typing import Any

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field

from src.domain.mcp.tool_argument_policy import ToolArgumentPolicy
from src.domain.mcp.value_objects import MCPServerConfig
from src.domain.mcp_registry.identity import (
    IdentityClaimPolicy,
    IdentityUnavailableError,
)
from src.infrastructure.logging import get_logger
from src.infrastructure.mcp.client_factory import HeaderProvider, MCPClientFactory

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

    # Design Ref: mcp-tool-category-routing module-2 —
    # args_schema는 모든 MCP 도구가 공유하는 제네릭 래퍼(MCPToolInput)라
    # 도구별 실제 입력 스키마를 담지 못한다. 서버가 list_tools로 준
    # inputSchema를 여기 보존해야 collect 노드가 근거 있는 인자를 만들 수 있다.
    # 스키마를 주지 않는 서버도 있으므로 기본은 빈 dict(= 스키마 미상).
    mcp_input_schema: dict[str, Any] = {}

    # Design Ref: fix-mcp-tool-call-not-reaching-server §4 —
    # ③ 실행 구간 로그의 추적 필드. 미주입(기본 "")이어도 기존 호출부는 그대로 동작한다.
    request_id: str = ""
    tool_id: str = ""

    # Design Ref: mcp-identity-header §1.1 — 신원 헤더가 필요한 서버면 로더가
    # 실행 주체로 만든 공급자를 넣는다. None 이면 기존과 동일 (FR-08).
    header_provider: HeaderProvider | None = None

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
        # Design Ref: §2.2 — "MCP tool execution started"의 유무가
        # "LLM이 도구를 호출했는가"와 "서버까지 갔는가"를 가르는 판정점이다.
        log_extra = {
            "request_id": self.request_id,
            "tool_id": self.tool_id,
            "server": self.server_config.name,
            "tool": self.mcp_tool_name,
        }

        # Design Ref: worker-context-injection §6.1 — 워커가 컨텍스트를 잃고
        # 지어낸 예시 URL은 서버에 도달하기 전에 차단한다. 예외가 아닌 지시성
        # 문자열을 반환해야 ToolMessage로 감싸여 워커가 자기 교정할 수 있다.
        blocked = ToolArgumentPolicy.find_placeholder(args)
        if blocked is not None:
            logger.warning(
                "MCP tool call blocked (placeholder argument)",
                reason="placeholder_url",
                blocked_value=blocked,
                **log_extra,
            )
            return ToolArgumentPolicy.build_blocked_message(blocked)

        logger.info("MCP tool execution started", **log_extra)
        return await self._call(args, log_extra)

    async def _call(self, args: dict[str, Any], log_extra: dict) -> str:
        """세션 생성 → call_tool. 신원 불가는 예외가 아닌 안내문으로 돌려준다."""
        try:
            # Design Ref: §4 — ③ 경로의 세션 로그도 같은 request_id로 이어야
            # 한 요청의 로그 체인이 끊기지 않는다.
            async with MCPClientFactory.create_session(
                self.server_config,
                self.request_id or None,
                header_provider=self.header_provider,
            ) as session:
                result = await session.call_tool(
                    name=self.mcp_tool_name,
                    arguments=args,
                )
        except IdentityUnavailableError as e:
            # Design Ref: mcp-identity-header §6.2 — 예상된 경로라 스택 없이 WARN.
            # placeholder 차단과 같이 ToolMessage 로 돌려줘야 사용자가 원인을 본다.
            logger.warning(
                "MCP tool call blocked (identity)",
                reason=e.reason,
                identity_sub=e.subject,  # Check G-4
                **log_extra,
            )
            return IdentityClaimPolicy.user_message(e)
        except Exception as e:
            logger.error(
                "MCP tool execution failed",
                exception=e,
                **log_extra,
            )
            raise

        content = MCPToolAdapter._extract_content(result)
        logger.info("MCP tool execution completed", **log_extra)
        return content

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
