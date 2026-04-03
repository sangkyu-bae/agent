"""MCP Client Factory.

Transport 방식(stdio/SSE/WebSocket)에 따라 MCP ClientSession을 생성한다.
infrastructure 레이어 — 비즈니스 규칙 없음.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client

from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class MCPClientFactory:
    """MCP 서버 연결 팩토리.

    Transport 방식에 따라 적절한 ClientSession 컨텍스트 매니저를 반환한다.
    """

    @staticmethod
    @asynccontextmanager
    async def create_session(
        config: MCPServerConfig,
        request_id: str | None = None,
    ) -> AsyncIterator[ClientSession]:
        """MCP 서버 세션을 생성하는 비동기 컨텍스트 매니저.

        Args:
            config: MCP 서버 설정
            request_id: 요청 추적 ID (로깅용)

        Yields:
            초기화된 ClientSession

        Raises:
            연결 실패 시 transport 레벨의 예외를 그대로 전파
        """
        log_extra = {
            "request_id": request_id,
            "server": config.name,
            "transport": config.transport.value,
        }

        logger.info("MCP session connecting", **log_extra)

        try:
            if config.transport == MCPTransport.STDIO:
                async with MCPClientFactory._stdio_session(config) as session:
                    logger.info("MCP session connected", **log_extra)
                    yield session

            elif config.transport == MCPTransport.SSE:
                async with MCPClientFactory._sse_session(config) as session:
                    logger.info("MCP session connected", **log_extra)
                    yield session

            else:  # WEBSOCKET
                async with MCPClientFactory._websocket_session(config) as session:
                    logger.info("MCP session connected", **log_extra)
                    yield session

        except Exception as e:
            logger.error(
                "MCP session connection failed",
                exception=e,
                **log_extra,
            )
            raise

        else:
            logger.info("MCP session closed", **log_extra)

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
    async def _sse_session(config: MCPServerConfig) -> AsyncIterator[ClientSession]:
        sse_cfg = config.sse
        headers = sse_cfg.headers or {}
        async with sse_client(
            url=sse_cfg.url,
            headers=headers,
            timeout=sse_cfg.timeout,
        ) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session

    @staticmethod
    @asynccontextmanager
    async def _websocket_session(config: MCPServerConfig) -> AsyncIterator[ClientSession]:
        from mcp.client.websocket import websocket_client

        ws_cfg = config.websocket
        async with websocket_client(url=ws_cfg.url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
