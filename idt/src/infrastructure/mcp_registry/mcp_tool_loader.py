"""MCPToolLoader: DB 등록 MCP 서버 → LangChain BaseTool 변환."""
from langchain_core.tools import BaseTool

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType
from src.domain.mcp.value_objects import (
    MCPServerConfig,
    MCPTransport,
    SSEServerConfig,
    StreamableHTTPServerConfig,
)
from src.infrastructure.mcp.client_factory import HeaderProvider
from src.infrastructure.mcp.tool_registry import MCPToolRegistry
from src.infrastructure.mcp_registry.smithery_url import build_streamable_http


class McpIdentityWiringError(RuntimeError):
    """신원 헤더가 필요한 서버인데 공급자 팩토리가 배선되지 않았다.

    헤더 없이 보내면 서버 설정에 따라 거부되거나(identity 모드) 고정 자원이
    열린다 — 조용히 넘어가지 않도록 호출 시점에 개발자 오류로 드러낸다.
    """


def _unwired_provider(server_id: str) -> HeaderProvider:
    async def provide() -> dict[str, str]:
        raise McpIdentityWiringError(
            f"identity header factory is not wired for MCP server {server_id!r}"
        )

    return provide


class MCPToolLoader:
    """
    MCPServerRegistration → MCPServerConfig(SSE/Streamable HTTP) 조립 후
    MCPToolRegistry(MCP-001)로 LangChain BaseTool 목록 반환.
    """

    def __init__(self, logger: LoggerInterface, identity_headers=None):
        """identity_headers: IdentityHeaderProviderFactory | None.

        도구를 실제로 실행하는 런타임 로더에만 주입한다. 목록 조회 전용
        경로(도구 동기화·연결 테스트)는 없어도 된다 — 도구를 부르지 않는다.
        """
        self._logger = logger
        self._identity_headers = identity_headers

    @staticmethod
    def _build_config(registration: MCPServerRegistration) -> MCPServerConfig:
        """transport에 맞는 MCPServerConfig를 조립한다."""
        if registration.transport == MCPTransportType.STREAMABLE_HTTP:
            url, headers = build_streamable_http(
                registration.endpoint,
                registration.auth_config,
                registration.server_config,
            )
            return MCPServerConfig(
                name=registration.tool_id,
                transport=MCPTransport.STREAMABLE_HTTP,
                streamable_http=StreamableHTTPServerConfig(
                    url=url, headers=headers or None
                ),
            )
        return MCPServerConfig(
            name=registration.tool_id,  # "mcp_{uuid}"
            transport=MCPTransport.SSE,
            sse=SSEServerConfig(url=registration.endpoint),
        )

    def _header_provider(
        self,
        registration: MCPServerRegistration,
        subject_user_id: str | None,
        request_id: str,
    ) -> HeaderProvider | None:
        """Design Ref: mcp-identity-header §2.1 — 미설정 서버는 None (FR-08)."""
        if not registration.requires_identity:
            return None
        if self._identity_headers is None:
            return _unwired_provider(registration.id)
        return self._identity_headers.for_registration(
            registration, subject_user_id, request_id
        )

    async def load(
        self,
        registration: MCPServerRegistration,
        request_id: str,
        subject_user_id: str | None = None,
    ) -> list[BaseTool]:
        """단일 MCP 서버 등록 정보 → LangChain BaseTool 목록."""
        self._logger.info(
            "MCPToolLoader load start",
            request_id=request_id,
            server_id=registration.id,
            server_name=registration.name,
            transport=registration.transport.value,
        )

        config = self._build_config(registration)
        provider = self._header_provider(registration, subject_user_id, request_id)
        registry = MCPToolRegistry(
            configs=[config], header_providers={config.name: provider}
        )
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
        subject_user_id: str | None = None,
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

        return await self.load(
            registration, request_id, subject_user_id=subject_user_id
        )
