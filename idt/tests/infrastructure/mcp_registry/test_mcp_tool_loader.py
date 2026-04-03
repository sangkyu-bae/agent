"""Infrastructure 테스트: MCPToolLoader."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.tools import BaseTool

from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType
from src.infrastructure.mcp_registry.mcp_tool_loader import MCPToolLoader


@pytest.fixture
def mock_logger():
    return MagicMock()


@pytest.fixture
def sample_registration():
    return MCPServerRegistration(
        id="uuid-001",
        user_id="user-1",
        name="Test MCP",
        description="desc",
        endpoint="https://mcp.example.com/sse",
        transport=MCPTransportType.SSE,
        input_schema=None,
        is_active=True,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


class TestMCPToolLoaderLoad:

    @pytest.mark.asyncio
    async def test_load_returns_tools_on_success(self, mock_logger, sample_registration):
        mock_tool = MagicMock(spec=BaseTool)

        with patch(
            "src.infrastructure.mcp_registry.mcp_tool_loader.MCPToolRegistry"
        ) as MockRegistry:
            instance = MockRegistry.return_value
            instance.get_tools = AsyncMock(return_value=[mock_tool])

            loader = MCPToolLoader(logger=mock_logger)
            tools = await loader.load(sample_registration, request_id="req-001")

        assert len(tools) == 1
        assert tools[0] is mock_tool

    @pytest.mark.asyncio
    async def test_load_builds_sse_config_from_registration(
        self, mock_logger, sample_registration
    ):
        with patch(
            "src.infrastructure.mcp_registry.mcp_tool_loader.MCPToolRegistry"
        ) as MockRegistry:
            instance = MockRegistry.return_value
            instance.get_tools = AsyncMock(return_value=[])

            loader = MCPToolLoader(logger=mock_logger)
            await loader.load(sample_registration, request_id="req-001")

            call_kwargs = MockRegistry.call_args[1]
            config = call_kwargs["configs"][0]

        assert config.name == "mcp_uuid-001"
        assert config.sse.url == "https://mcp.example.com/sse"

    @pytest.mark.asyncio
    async def test_load_raises_on_connection_error(self, mock_logger, sample_registration):
        with patch(
            "src.infrastructure.mcp_registry.mcp_tool_loader.MCPToolRegistry"
        ) as MockRegistry:
            instance = MockRegistry.return_value
            instance.get_tools = AsyncMock(side_effect=ConnectionError("refused"))

            loader = MCPToolLoader(logger=mock_logger)
            with pytest.raises(ConnectionError):
                await loader.load(sample_registration, request_id="req-001")


class TestMCPToolLoaderLoadByToolId:

    @pytest.mark.asyncio
    async def test_load_by_tool_id_returns_first_tool(self, mock_logger, sample_registration):
        mock_tool = MagicMock(spec=BaseTool)
        mock_repo = AsyncMock()
        mock_repo.find_by_id.return_value = sample_registration  # id="uuid-001"

        with patch(
            "src.infrastructure.mcp_registry.mcp_tool_loader.MCPToolRegistry"
        ) as MockRegistry:
            instance = MockRegistry.return_value
            instance.get_tools = AsyncMock(return_value=[mock_tool])

            loader = MCPToolLoader(logger=mock_logger)
            result = await loader.load_by_tool_id(
                tool_id="mcp_uuid-001",
                repository=mock_repo,
                request_id="req-001",
            )

        assert len(result) == 1
        mock_repo.find_by_id.assert_called_once_with("uuid-001", "req-001")

    @pytest.mark.asyncio
    async def test_load_by_tool_id_returns_empty_when_not_found(self, mock_logger):
        mock_repo = AsyncMock()
        mock_repo.find_by_id.return_value = None

        loader = MCPToolLoader(logger=mock_logger)
        result = await loader.load_by_tool_id(
            tool_id="mcp_missing",
            repository=mock_repo,
            request_id="req-001",
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_load_by_tool_id_strips_mcp_prefix(self, mock_logger, sample_registration):
        mock_repo = AsyncMock()
        mock_repo.find_by_id.return_value = sample_registration

        with patch(
            "src.infrastructure.mcp_registry.mcp_tool_loader.MCPToolRegistry"
        ) as MockRegistry:
            instance = MockRegistry.return_value
            instance.get_tools = AsyncMock(return_value=[])

            loader = MCPToolLoader(logger=mock_logger)
            await loader.load_by_tool_id(
                tool_id="mcp_uuid-001",
                repository=mock_repo,
                request_id="req-001",
            )

        # find_by_id는 "mcp_" 접두사를 제거한 "uuid-001"로 호출
        mock_repo.find_by_id.assert_called_once_with("uuid-001", "req-001")
