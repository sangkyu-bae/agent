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
