"""MCPClientFactory 테스트 — Mock 사용."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestMCPClientFactory:

    @pytest.mark.asyncio
    async def test_create_session_stdio_calls_stdio_client(self):
        from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport, StdioServerConfig
        from src.infrastructure.mcp.client_factory import MCPClientFactory

        config = MCPServerConfig(
            name="test",
            transport=MCPTransport.STDIO,
            stdio=StdioServerConfig(command="python", args=["server.py"]),
        )

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()

        with patch("src.infrastructure.mcp.client_factory.stdio_client") as mock_stdio, \
             patch("src.infrastructure.mcp.client_factory.ClientSession") as mock_cls:

            mock_read = AsyncMock()
            mock_write = AsyncMock()
            mock_stdio.return_value.__aenter__ = AsyncMock(return_value=(mock_read, mock_write))
            mock_stdio.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            async with MCPClientFactory.create_session(config, "req-001") as session:
                assert session is mock_session

        mock_stdio.assert_called_once()
        mock_session.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_session_sse_calls_sse_client(self):
        from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport, SSEServerConfig
        from src.infrastructure.mcp.client_factory import MCPClientFactory

        config = MCPServerConfig(
            name="remote",
            transport=MCPTransport.SSE,
            sse=SSEServerConfig(url="http://localhost:8080/sse"),
        )

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()

        with patch("src.infrastructure.mcp.client_factory.sse_client") as mock_sse, \
             patch("src.infrastructure.mcp.client_factory.ClientSession") as mock_cls:

            mock_read = AsyncMock()
            mock_write = AsyncMock()
            mock_sse.return_value.__aenter__ = AsyncMock(return_value=(mock_read, mock_write))
            mock_sse.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            async with MCPClientFactory.create_session(config, "req-002") as session:
                assert session is mock_session

        mock_sse.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_session_raises_on_connection_failure(self):
        from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport, StdioServerConfig
        from src.infrastructure.mcp.client_factory import MCPClientFactory

        config = MCPServerConfig(
            name="broken",
            transport=MCPTransport.STDIO,
            stdio=StdioServerConfig(command="nonexistent", args=[]),
        )

        with patch("src.infrastructure.mcp.client_factory.stdio_client") as mock_stdio:
            mock_stdio.return_value.__aenter__ = AsyncMock(
                side_effect=FileNotFoundError("command not found")
            )
            mock_stdio.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(FileNotFoundError):
                async with MCPClientFactory.create_session(config):
                    pass


class TestMCPClientFactoryStreamableHTTP:

    @pytest.mark.asyncio
    async def test_create_session_streamable_http_yields_session(self):
        from src.domain.mcp.value_objects import (
            MCPServerConfig,
            MCPTransport,
            StreamableHTTPServerConfig,
        )
        from src.infrastructure.mcp.client_factory import MCPClientFactory

        config = MCPServerConfig(
            name="http_server",
            transport=MCPTransport.STREAMABLE_HTTP,
            streamable_http=StreamableHTTPServerConfig(url="http://localhost:8080/mcp"),
        )

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()

        with patch("src.infrastructure.mcp.client_factory.streamablehttp_client") as mock_http, \
             patch("src.infrastructure.mcp.client_factory.ClientSession") as mock_cls:

            mock_read, mock_write, mock_get_id = AsyncMock(), AsyncMock(), MagicMock()
            # streamablehttp_client는 3-tuple (read, write, get_session_id)를 yield
            mock_http.return_value.__aenter__ = AsyncMock(
                return_value=(mock_read, mock_write, mock_get_id)
            )
            mock_http.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            async with MCPClientFactory.create_session(config, "req-http") as session:
                assert session is mock_session

        mock_http.assert_called_once()
        mock_session.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_streamable_http_injects_timeout(self):
        from src.domain.mcp.value_objects import (
            MCPServerConfig,
            MCPTimeoutConfig,
            MCPTransport,
            StreamableHTTPServerConfig,
        )
        from src.infrastructure.mcp.client_factory import MCPClientFactory

        config = MCPServerConfig(
            name="http_server",
            transport=MCPTransport.STREAMABLE_HTTP,
            streamable_http=StreamableHTTPServerConfig(url="http://localhost:8080/mcp"),
        )

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()

        with patch("src.infrastructure.mcp.client_factory.streamablehttp_client") as mock_http, \
             patch("src.infrastructure.mcp.client_factory.ClientSession") as mock_cls:

            mock_http.return_value.__aenter__ = AsyncMock(
                return_value=(AsyncMock(), AsyncMock(), MagicMock())
            )
            mock_http.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            timeout = MCPTimeoutConfig(connect=7.0, read=120.0)
            async with MCPClientFactory.create_session(config, timeout=timeout):
                pass

        kwargs = mock_http.call_args.kwargs
        assert kwargs["timeout"] == 7.0
        assert kwargs["sse_read_timeout"] == 120.0

    @pytest.mark.asyncio
    async def test_streamable_http_merges_auth_headers_with_priority(self):
        from src.domain.mcp.value_objects import (
            MCPAuthConfig,
            MCPServerConfig,
            MCPTransport,
            StreamableHTTPServerConfig,
        )
        from src.infrastructure.mcp.client_factory import MCPClientFactory

        config = MCPServerConfig(
            name="http_server",
            transport=MCPTransport.STREAMABLE_HTTP,
            streamable_http=StreamableHTTPServerConfig(
                url="http://localhost:8080/mcp",
                headers={"X-Static": "s", "Authorization": "Bearer OLD"},
            ),
        )

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()

        with patch("src.infrastructure.mcp.client_factory.streamablehttp_client") as mock_http, \
             patch("src.infrastructure.mcp.client_factory.ClientSession") as mock_cls:

            mock_http.return_value.__aenter__ = AsyncMock(
                return_value=(AsyncMock(), AsyncMock(), MagicMock())
            )
            mock_http.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            auth = MCPAuthConfig(token="NEW")
            async with MCPClientFactory.create_session(config, auth=auth):
                pass

        headers = mock_http.call_args.kwargs["headers"]
        assert headers["X-Static"] == "s"          # 정적 헤더 보존
        assert headers["Authorization"] == "Bearer NEW"  # auth 우선

    @pytest.mark.asyncio
    async def test_sse_injects_read_timeout(self):
        from src.domain.mcp.value_objects import (
            MCPServerConfig,
            MCPTimeoutConfig,
            MCPTransport,
            SSEServerConfig,
        )
        from src.infrastructure.mcp.client_factory import MCPClientFactory

        config = MCPServerConfig(
            name="remote",
            transport=MCPTransport.SSE,
            sse=SSEServerConfig(url="http://localhost:8080/sse"),
        )

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()

        with patch("src.infrastructure.mcp.client_factory.sse_client") as mock_sse, \
             patch("src.infrastructure.mcp.client_factory.ClientSession") as mock_cls:

            mock_sse.return_value.__aenter__ = AsyncMock(
                return_value=(AsyncMock(), AsyncMock())
            )
            mock_sse.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            timeout = MCPTimeoutConfig(connect=9.0, read=45.0)
            async with MCPClientFactory.create_session(config, timeout=timeout):
                pass

        kwargs = mock_sse.call_args.kwargs
        assert kwargs["timeout"] == 9.0
        assert kwargs["sse_read_timeout"] == 45.0
