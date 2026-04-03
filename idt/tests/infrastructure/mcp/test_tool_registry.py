"""MCPToolRegistry 테스트 — Mock 사용."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def single_stdio_config():
    from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport, StdioServerConfig
    return [
        MCPServerConfig(
            name="server1",
            transport=MCPTransport.STDIO,
            stdio=StdioServerConfig(command="npx", args=["server1"]),
        )
    ]


class TestMCPToolRegistry:

    def test_init_raises_when_too_many_servers(self):
        from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport, StdioServerConfig
        from src.infrastructure.mcp.tool_registry import MCPToolRegistry
        configs = [
            MCPServerConfig(
                name=f"server{i}",
                transport=MCPTransport.STDIO,
                stdio=StdioServerConfig(command="npx", args=[]),
            )
            for i in range(21)
        ]
        with pytest.raises(ValueError, match="Too many MCP servers"):
            MCPToolRegistry(configs)

    def test_init_succeeds_at_max_limit(self):
        from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport, StdioServerConfig
        from src.infrastructure.mcp.tool_registry import MCPToolRegistry
        configs = [
            MCPServerConfig(
                name=f"server{i}",
                transport=MCPTransport.STDIO,
                stdio=StdioServerConfig(command="npx", args=[]),
            )
            for i in range(20)
        ]
        registry = MCPToolRegistry(configs)
        assert registry is not None

    @pytest.mark.asyncio
    async def test_get_tools_returns_langchain_tools(self, single_stdio_config):
        from src.infrastructure.mcp.tool_registry import MCPToolRegistry
        from langchain_core.tools import BaseTool

        mock_mcp_tool = MagicMock()
        mock_mcp_tool.name = "read_file"
        mock_mcp_tool.description = "Read a file"

        mock_session = AsyncMock()
        mock_session.list_tools = AsyncMock(
            return_value=MagicMock(tools=[mock_mcp_tool])
        )

        with patch(
            "src.infrastructure.mcp.tool_registry.MCPClientFactory.create_session"
        ) as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            registry = MCPToolRegistry(single_stdio_config)
            tools = await registry.get_tools(request_id="req-001")

        assert len(tools) == 1
        assert isinstance(tools[0], BaseTool)
        assert tools[0].name == "server1_read_file"

    @pytest.mark.asyncio
    async def test_get_tools_sanitizes_tool_name(self, single_stdio_config):
        from src.infrastructure.mcp.tool_registry import MCPToolRegistry

        mock_mcp_tool = MagicMock()
        mock_mcp_tool.name = "list-resources"  # 하이픈 포함
        mock_mcp_tool.description = "List resources"

        mock_session = AsyncMock()
        mock_session.list_tools = AsyncMock(
            return_value=MagicMock(tools=[mock_mcp_tool])
        )

        with patch(
            "src.infrastructure.mcp.tool_registry.MCPClientFactory.create_session"
        ) as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            registry = MCPToolRegistry(single_stdio_config)
            tools = await registry.get_tools()

        assert tools[0].name == "server1_list_resources"

    @pytest.mark.asyncio
    async def test_get_tools_returns_empty_list_when_server_fails(self, single_stdio_config):
        from src.infrastructure.mcp.tool_registry import MCPToolRegistry

        with patch(
            "src.infrastructure.mcp.tool_registry.MCPClientFactory.create_session"
        ) as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(
                side_effect=ConnectionError("server down")
            )
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            registry = MCPToolRegistry(single_stdio_config)
            tools = await registry.get_tools()

        # 서버 연결 실패 시 빈 리스트 반환 (전체 실패 방지)
        assert tools == []

    @pytest.mark.asyncio
    async def test_get_tools_aggregates_multiple_servers(self):
        from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport, StdioServerConfig
        from src.infrastructure.mcp.tool_registry import MCPToolRegistry

        configs = [
            MCPServerConfig(
                name="serverA",
                transport=MCPTransport.STDIO,
                stdio=StdioServerConfig(command="npx", args=[]),
            ),
            MCPServerConfig(
                name="serverB",
                transport=MCPTransport.STDIO,
                stdio=StdioServerConfig(command="npx", args=[]),
            ),
        ]

        tool_a = MagicMock(name="tool_a", description="Tool A")
        tool_a.name = "tool_a"
        tool_a.description = "Tool A"
        tool_b = MagicMock(name="tool_b", description="Tool B")
        tool_b.name = "tool_b"
        tool_b.description = "Tool B"

        call_count = 0

        async def make_session_enter(*args, **kwargs):
            nonlocal call_count
            session = AsyncMock()
            if call_count == 0:
                session.list_tools = AsyncMock(
                    return_value=MagicMock(tools=[tool_a])
                )
            else:
                session.list_tools = AsyncMock(
                    return_value=MagicMock(tools=[tool_b])
                )
            call_count += 1
            return session

        with patch(
            "src.infrastructure.mcp.tool_registry.MCPClientFactory.create_session"
        ) as mock_ctx:
            mock_ctx.return_value.__aenter__ = make_session_enter
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            registry = MCPToolRegistry(configs)
            tools = await registry.get_tools()

        assert len(tools) == 2
