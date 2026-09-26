"""MCP Client Factory.

Transport 방식(stdio/SSE/WebSocket/Streamable HTTP)에 따라 MCP ClientSession을 생성한다.
타임아웃·인증 헤더를 주입받아 transport 세션에 반영한다.
infrastructure 레이어 — 비즈니스 규칙 없음.
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client

from src.domain.mcp.value_objects import (
    MCPAuthConfig,
    MCPServerConfig,
    MCPTimeoutConfig,
    MCPTransport,
)
from src.domain.mcp_registry.identity import IdentityUnavailableError
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)

# Design Ref: mcp-identity-header §1.1 — 호출 시점 헤더 공급자.
# 세션을 열기 직전에 불리며, 실패하면 연결을 시도하지 않는다.
HeaderProvider = Callable[[], Awaitable[dict[str, str]]]


class HeaderProviderError(RuntimeError):
    """헤더 공급자 단계 실패(서명 오류·배선 오류·설정 손상) — 연결 전이다.

    Check G-2: 호출자가 '대상 서버에 아무것도 보내지 않았다'를 구분할 수 있게
    감싼다. 신원 불가(IdentityUnavailableError)는 사용자 안내가 필요해 감싸지 않는다.
    """


def _overlay(base: dict[str, str], extra: dict[str, str]) -> dict[str, str]:
    """HTTP 헤더는 대소문자 무관 — 같은 이름의 기존 키를 지우고 덮는다."""
    lowered = {key.lower() for key in extra}
    merged = {k: v for k, v in base.items() if k.lower() not in lowered}
    merged.update(extra)
    return merged


def _merge_headers(
    static_headers: dict[str, str] | None,
    auth: MCPAuthConfig | None,
    issued: dict[str, str] | None = None,
) -> dict[str, str]:
    """정적 → auth → 발급 헤더 순으로 덮는다. 발급 헤더가 최후 순위다 (§7)."""
    merged = dict(static_headers or {})
    if auth is not None:
        merged = _overlay(merged, auth.to_headers())
    if issued:
        merged = _overlay(merged, issued)
    return merged


_HEADER_TRANSPORTS = frozenset({MCPTransport.SSE, MCPTransport.STREAMABLE_HTTP})


async def _issue_headers(
    config: MCPServerConfig, header_provider: HeaderProvider | None
) -> dict[str, str] | None:
    """공급자를 연결 전에 부른다. 헤더를 실을 수 없는 transport 면 거부한다
    — 신원 헤더를 조용히 버리고 연결하면 서버 설정에 따라 타인 자원이 열린다."""
    if header_provider is None:
        return None
    if config.transport not in _HEADER_TRANSPORTS:
        raise ValueError(
            f"identity headers require an HTTP transport, got {config.transport.value}"
        )
    try:
        return await header_provider()
    except IdentityUnavailableError:
        raise
    except Exception as e:
        raise HeaderProviderError(
            f"identity header provider failed ({type(e).__name__})"
        ) from e


class MCPClientFactory:
    """MCP 서버 연결 팩토리.

    Transport 방식에 따라 적절한 ClientSession 컨텍스트 매니저를 반환한다.
    """

    @staticmethod
    @asynccontextmanager
    async def create_session(
        config: MCPServerConfig,
        request_id: str | None = None,
        *,
        timeout: MCPTimeoutConfig | None = None,
        auth: MCPAuthConfig | None = None,
        header_provider: HeaderProvider | None = None,
    ) -> AsyncIterator[ClientSession]:
        """MCP 서버 세션을 생성하는 비동기 컨텍스트 매니저.

        Args:
            config: MCP 서버 설정
            request_id: 요청 추적 ID (로깅용)
            timeout: 세분화 타임아웃 (None이면 기본값)
            auth: 인증 헤더 주입 설정 (None이면 미적용)
            header_provider: 호출 시점 헤더 공급자 (신원 헤더). 연결 전에 불리며
                예외(IdentityUnavailableError 등)는 연결 없이 그대로 전파된다.

        Yields:
            초기화된 ClientSession

        Raises:
            연결 실패 시 transport 레벨의 예외를 그대로 전파
        """
        timeout = timeout or MCPTimeoutConfig()
        issued = await _issue_headers(config, header_provider)
        log_extra = {
            "request_id": request_id,
            "server": config.name,
            "transport": config.transport.value,
        }

        logger.info("MCP session connecting", **log_extra)

        try:
            async with MCPClientFactory._dispatch_session(
                config, timeout, auth, issued
            ) as session:
                logger.info("MCP session connected", **log_extra)
                yield session
        except Exception as e:
            logger.error("MCP session connection failed", exception=e, **log_extra)
            raise
        else:
            logger.info("MCP session closed", **log_extra)

    @staticmethod
    @asynccontextmanager
    async def _dispatch_session(
        config: MCPServerConfig,
        timeout: MCPTimeoutConfig,
        auth: MCPAuthConfig | None,
        issued: dict[str, str] | None = None,
    ) -> AsyncIterator[ClientSession]:
        """transport 분기 — 각 세션 헬퍼로 위임한다."""
        if config.transport == MCPTransport.STDIO:
            async with MCPClientFactory._stdio_session(config) as session:
                yield session
        elif config.transport == MCPTransport.SSE:
            async with MCPClientFactory._sse_session(
                config, timeout, auth, issued
            ) as session:
                yield session
        elif config.transport == MCPTransport.STREAMABLE_HTTP:
            async with MCPClientFactory._streamable_http_session(
                config, timeout, auth, issued
            ) as session:
                yield session
        else:  # WEBSOCKET
            async with MCPClientFactory._websocket_session(config) as session:
                yield session

    @staticmethod
    @asynccontextmanager
    async def _stdio_session(config: MCPServerConfig) -> AsyncIterator[ClientSession]:
        stdio_cfg = config.stdio
        params = StdioServerParameters(
            command=stdio_cfg.command,
            args=stdio_cfg.args,
            env=stdio_cfg.env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    @staticmethod
    @asynccontextmanager
    async def _sse_session(
        config: MCPServerConfig,
        timeout: MCPTimeoutConfig,
        auth: MCPAuthConfig | None,
        issued: dict[str, str] | None = None,
    ) -> AsyncIterator[ClientSession]:
        sse_cfg = config.sse
        headers = _merge_headers(sse_cfg.headers, auth, issued)
        async with sse_client(
            url=sse_cfg.url,
            headers=headers,
            timeout=timeout.connect,
            sse_read_timeout=timeout.read,
        ) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    @staticmethod
    @asynccontextmanager
    async def _streamable_http_session(
        config: MCPServerConfig,
        timeout: MCPTimeoutConfig,
        auth: MCPAuthConfig | None,
        issued: dict[str, str] | None = None,
    ) -> AsyncIterator[ClientSession]:
        http_cfg = config.streamable_http
        # config에 자체 타임아웃이 있으면 우선, 없으면 주입 타임아웃 사용
        effective_timeout = http_cfg.timeout or timeout
        headers = _merge_headers(http_cfg.headers, auth, issued)
        # streamablehttp_client는 3-tuple (read, write, get_session_id)를 yield
        async with streamablehttp_client(
            url=http_cfg.url,
            headers=headers,
            timeout=effective_timeout.connect,
            sse_read_timeout=effective_timeout.read,
        ) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    @staticmethod
    @asynccontextmanager
    async def _websocket_session(
        config: MCPServerConfig,
    ) -> AsyncIterator[ClientSession]:
        from mcp.client.websocket import websocket_client

        ws_cfg = config.websocket
        async with websocket_client(url=ws_cfg.url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
