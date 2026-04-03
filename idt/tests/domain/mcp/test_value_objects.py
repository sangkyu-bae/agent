"""Domain Value Objects 테스트 - Mock 금지."""
import pytest
from pydantic import ValidationError


class TestMCPTransport:
    def test_stdio_value(self):
        from src.domain.mcp.value_objects import MCPTransport
        assert MCPTransport.STDIO.value == "stdio"

    def test_sse_value(self):
        from src.domain.mcp.value_objects import MCPTransport
        assert MCPTransport.SSE.value == "sse"

    def test_websocket_value(self):
        from src.domain.mcp.value_objects import MCPTransport
        assert MCPTransport.WEBSOCKET.value == "websocket"


class TestStdioServerConfig:
    def test_create_with_required_fields(self):
        from src.domain.mcp.value_objects import StdioServerConfig
        config = StdioServerConfig(command="npx", args=["-y", "server"])
        assert config.command == "npx"
        assert config.args == ["-y", "server"]
        assert config.env is None

    def test_args_defaults_to_empty_list(self):
        from src.domain.mcp.value_objects import StdioServerConfig
        config = StdioServerConfig(command="python")
        assert config.args == []

    def test_raises_when_command_missing(self):
        from src.domain.mcp.value_objects import StdioServerConfig
        with pytest.raises(ValidationError):
            StdioServerConfig()


class TestSSEServerConfig:
    def test_create_with_url(self):
        from src.domain.mcp.value_objects import SSEServerConfig
        config = SSEServerConfig(url="http://localhost:8080/sse")
        assert config.url == "http://localhost:8080/sse"
        assert config.timeout == 30.0
        assert config.headers is None

    def test_custom_timeout(self):
        from src.domain.mcp.value_objects import SSEServerConfig
        config = SSEServerConfig(url="http://test.com/sse", timeout=60.0)
        assert config.timeout == 60.0


class TestWebSocketServerConfig:
    def test_create_with_url(self):
        from src.domain.mcp.value_objects import WebSocketServerConfig
        config = WebSocketServerConfig(url="ws://localhost:8081/ws")
        assert config.url == "ws://localhost:8081/ws"
        assert config.timeout == 30.0


class TestMCPServerConfig:
    def test_get_transport_config_returns_stdio_config(self):
        from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport, StdioServerConfig
        config = MCPServerConfig(
            name="filesystem",
            transport=MCPTransport.STDIO,
            stdio=StdioServerConfig(command="npx", args=["-y", "server"]),
        )
        result = config.get_transport_config()
        assert isinstance(result, StdioServerConfig)
        assert result.command == "npx"

    def test_get_transport_config_returns_sse_config(self):
        from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport, SSEServerConfig
        config = MCPServerConfig(
            name="remote",
            transport=MCPTransport.SSE,
            sse=SSEServerConfig(url="http://test.com/sse"),
        )
        result = config.get_transport_config()
        assert isinstance(result, SSEServerConfig)

    def test_get_transport_config_returns_websocket_config(self):
        from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport, WebSocketServerConfig
        config = MCPServerConfig(
            name="ws_server",
            transport=MCPTransport.WEBSOCKET,
            websocket=WebSocketServerConfig(url="ws://test.com/ws"),
        )
        result = config.get_transport_config()
        assert isinstance(result, WebSocketServerConfig)

    def test_get_transport_config_raises_when_stdio_missing(self):
        from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport
        config = MCPServerConfig(name="test", transport=MCPTransport.STDIO)
        with pytest.raises(ValueError, match="stdio config is required"):
            config.get_transport_config()

    def test_get_transport_config_raises_when_sse_missing(self):
        from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport
        config = MCPServerConfig(name="test", transport=MCPTransport.SSE)
        with pytest.raises(ValueError, match="sse config is required"):
            config.get_transport_config()

    def test_get_transport_config_raises_when_websocket_missing(self):
        from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport
        config = MCPServerConfig(name="test", transport=MCPTransport.WEBSOCKET)
        with pytest.raises(ValueError, match="websocket config is required"):
            config.get_transport_config()


class TestMCPToolResult:
    def test_create_success_result(self):
        from src.domain.mcp.value_objects import MCPToolResult
        result = MCPToolResult(
            tool_name="read_file",
            server_name="filesystem",
            content="file content here",
        )
        assert result.tool_name == "read_file"
        assert result.server_name == "filesystem"
        assert result.content == "file content here"
        assert result.is_error is False

    def test_create_error_result(self):
        from src.domain.mcp.value_objects import MCPToolResult
        result = MCPToolResult(
            tool_name="read_file",
            server_name="filesystem",
            content="File not found",
            is_error=True,
        )
        assert result.is_error is True
