"""MCPToolUseCase 테스트 — Mock 사용."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def stdio_configs():
    from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport, StdioServerConfig
    return [
        MCPServerConfig(
            name="filesystem",
            transport=MCPTransport.STDIO,
            stdio=StdioServerConfig(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            ),
        )
    ]


class TestMCPToolUseCase:

    @pytest.mark.asyncio
    async def test_get_tools_for_agent_returns_tool_list(self, stdio_configs):
        from src.application.mcp.use_case import MCPToolUseCase

        mock_tool = MagicMock()
        use_case = MCPToolUseCase(stdio_configs)

        with patch.object(
            use_case._registry, "get_tools", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = [mock_tool]
            tools = await use_case.get_tools_for_agent("req-001")

        assert len(tools) == 1
        mock_get.assert_called_once_with("req-001")

    @pytest.mark.asyncio
    async def test_get_tools_for_agent_returns_empty_when_no_tools(self, stdio_configs):
        from src.application.mcp.use_case import MCPToolUseCase

        use_case = MCPToolUseCase(stdio_configs)

        with patch.object(
            use_case._registry, "get_tools", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = []
            tools = await use_case.get_tools_for_agent("req-002")

        assert tools == []

    @pytest.mark.asyncio
    async def test_get_tools_for_agent_passes_request_id_to_registry(self, stdio_configs):
        from src.application.mcp.use_case import MCPToolUseCase

        use_case = MCPToolUseCase(stdio_configs)

        with patch.object(
            use_case._registry, "get_tools", new_callable=AsyncMock
        ) as mock_get:
            mock_get.return_value = []
            await use_case.get_tools_for_agent("req-xyz-999")

        mock_get.assert_called_once_with("req-xyz-999")

    def test_use_case_creates_registry_with_configs(self, stdio_configs):
        from src.application.mcp.use_case import MCPToolUseCase
        from src.infrastructure.mcp.tool_registry import MCPToolRegistry

        use_case = MCPToolUseCase(stdio_configs)
        assert isinstance(use_case._registry, MCPToolRegistry)

    def test_use_case_raises_when_too_many_servers(self):
        from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport, StdioServerConfig
        from src.application.mcp.use_case import MCPToolUseCase

        configs = [
            MCPServerConfig(
                name=f"server{i}",
                transport=MCPTransport.STDIO,
                stdio=StdioServerConfig(command="npx", args=[]),
            )
            for i in range(21)
        ]
        with pytest.raises(ValueError, match="Too many MCP servers"):
            MCPToolUseCase(configs)
