"""MCPToolAdapter 테스트 — Mock 사용."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def stdio_server_config():
    from src.domain.mcp.value_objects import MCPServerConfig, MCPTransport, StdioServerConfig
    return MCPServerConfig(
        name="test_server",
        transport=MCPTransport.STDIO,
        stdio=StdioServerConfig(command="python", args=["server.py"]),
    )


@pytest.fixture
def adapter(stdio_server_config):
    from src.infrastructure.mcp.tool_adapter import MCPToolAdapter
    return MCPToolAdapter(
        name="test_server_read_file",
        description="Read a file from the filesystem",
        server_config=stdio_server_config,
        mcp_tool_name="read_file",
    )


class TestMCPToolAdapter:

    def test_adapter_is_langchain_base_tool(self, adapter):
        from langchain_core.tools import BaseTool
        assert isinstance(adapter, BaseTool)

    def test_adapter_name_set_correctly(self, adapter):
        assert adapter.name == "test_server_read_file"

    def test_adapter_description_set_correctly(self, adapter):
        assert "file" in adapter.description.lower()

    @pytest.mark.asyncio
    async def test_arun_returns_text_content_on_success(self, adapter):
        # Given
        mock_content_item = MagicMock()
        mock_content_item.text = "file content here"
        mock_result = MagicMock()
        mock_result.content = [mock_content_item]

        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        with patch(
            "src.infrastructure.mcp.tool_adapter.MCPClientFactory.create_session"
        ) as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            # When
            result = await adapter._arun(arguments={"path": "/tmp/test.txt"})

        # Then
        assert result == "file content here"
        mock_session.call_tool.assert_called_once_with(
            name="read_file",
            arguments={"path": "/tmp/test.txt"},
        )

    @pytest.mark.asyncio
    async def test_arun_with_no_arguments_passes_empty_dict(self, adapter):
        # Given
        mock_result = MagicMock()
        mock_result.content = [MagicMock(text="ok")]

        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        with patch(
            "src.infrastructure.mcp.tool_adapter.MCPClientFactory.create_session"
        ) as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await adapter._arun()

        mock_session.call_tool.assert_called_once_with(name="read_file", arguments={})

    @pytest.mark.asyncio
    async def test_arun_concatenates_multiple_content_items(self, adapter):
        # Given
        mock_result = MagicMock()
        mock_result.content = [
            MagicMock(text="line1"),
            MagicMock(text="line2"),
        ]

        mock_session = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        with patch(
            "src.infrastructure.mcp.tool_adapter.MCPClientFactory.create_session"
        ) as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            result = await adapter._arun()

        assert result == "line1\nline2"

    @pytest.mark.asyncio
    async def test_arun_raises_on_connection_error(self, adapter):
        # Given
        with patch(
            "src.infrastructure.mcp.tool_adapter.MCPClientFactory.create_session"
        ) as mock_ctx:
            mock_ctx.return_value.__aenter__ = AsyncMock(
                side_effect=ConnectionError("Connection refused")
            )
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)

            # When & Then
            with pytest.raises(ConnectionError):
                await adapter._arun()

    def test_extract_content_from_text_items(self):
        from src.infrastructure.mcp.tool_adapter import MCPToolAdapter
        mock_item = MagicMock()
        mock_item.text = "hello"
        mock_result = MagicMock()
        mock_result.content = [mock_item]
        assert MCPToolAdapter._extract_content(mock_result) == "hello"

    def test_extract_content_returns_empty_string_when_no_content(self):
        from src.infrastructure.mcp.tool_adapter import MCPToolAdapter
        mock_result = MagicMock()
        mock_result.content = []
        assert MCPToolAdapter._extract_content(mock_result) == ""
