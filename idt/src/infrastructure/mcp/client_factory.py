"""MCP Client Factory.

Transport 방식(stdio/SSE/WebSocket/Streamable HTTP)에 따라 MCP ClientSession을 생성한다.
타임아웃·인증 헤더를 주입받아 transport 세션에 반영한다.
infrastructure 레이어 — 비즈니스 규칙 없음.
"""

from collections.abc import AsyncIterator
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
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


def _merge_headers(
    static_headers: dict[str, str] | None,
    auth: MCPAuthConfig | None,
) -> dict[str, str]:
    """정적 헤더에 인증 헤더를 오버레이한다. 충돌 시 auth가 우선한다."""
    merged = dict(static_headers or {})
    if auth is not None:
        merged.update(auth.to_headers())
    return merged


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
    ) -> AsyncIterator[ClientSession]:
        """MCP 서버 세션을 생성하는 비동기 컨텍스트 매니저.

        Args:
            config: MCP 서버 설정
            request_id: 요청 추적 ID (로깅용)
            timeout: 세분화 타임아웃 (None이면 기본값)
            auth: 인증 헤더 주입 설정 (None이면 미적용)

        Yields:
            초기화된 ClientSession

        Raises:
            연결 실패 시 transport 레벨의 예외를 그대로 전파
        """
        timeout = timeout or MCPTimeoutConfig()
        log_extra = {
            "request_id": request_id,
            "server": config.name,
            "transport": config.transport.value,
        }

        logger.info("MCP session connecting", **log_extra)

        try:
            async with MCPClientFactory._dispatch_session(
                config, timeout, auth
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
    ) -> AsyncIterator[ClientSession]:
        """transport 분기 — 각 세션 헬퍼로 위임한다."""
        if config.transport == MCPTransport.STDIO:
            async with MCPClientFactory._stdio_session(config) as session:
                yield session
        elif config.transport == MCPTransport.SSE:
            async with MCPClientFactory._sse_session(config, timeout, auth) as session:
                yield session
        elif config.transport == MCPTransport.STREAMABLE_HTTP:
            async with MCPClientFactory._streamable_http_session(
                config, timeout, auth
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
    ) -> AsyncIterator[ClientSession]:
        sse_cfg = config.sse
        headers = _merge_headers(sse_cfg.headers, auth)
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
    ) -> AsyncIterator[ClientSession]:
        http_cfg = config.streamable_http
        # config에 자체 타임아웃이 있으면 우선, 없으면 주입 타임아웃 사용
        effective_timeout = http_cfg.timeout or timeout
        headers = _merge_headers(http_cfg.headers, auth)
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
