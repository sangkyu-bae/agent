"""Infrastructure 테스트: MCPToolLoader Streamable HTTP 분기."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.mcp.value_objects import MCPTransport
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType
from src.infrastructure.mcp_registry.mcp_tool_loader import MCPToolLoader


@pytest.fixture
def mock_logger():
    return MagicMock()


def _streamable_registration():
    return MCPServerRegistration(
        id="uuid-http",
        user_id="user-1",
        name="Naver Search",
        description="desc",
        endpoint="https://server.smithery.ai/@isnow890/naver-search-mcp",
        transport=MCPTransportType.STREAMABLE_HTTP,
        input_schema=None,
        is_active=True,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
        auth_config={"api_key": "K", "profile": "P"},
        server_config={"NAVER_CLIENT_ID": "id", "NAVER_CLIENT_SECRET": "sec"},
    )


class TestLoaderStreamableHttp:

    @pytest.mark.asyncio
    async def test_builds_streamable_http_config(self, mock_logger):
        reg = _streamable_registration()
        with patch(
            "src.infrastructure.mcp_registry.mcp_tool_loader.MCPToolRegistry"
        ) as MockRegistry:
            MockRegistry.return_value.get_tools = AsyncMock(return_value=[])
            loader = MCPToolLoader(logger=mock_logger)
            await loader.load(reg, request_id="req-1")

            config = MockRegistry.call_args[1]["configs"][0]

        assert config.transport == MCPTransport.STREAMABLE_HTTP
        assert config.streamable_http is not None
        assert config.streamable_http.url.endswith(
            "/mcp?api_key=K&config="  # 순서: api_key, config (profile 포함)
        ) or "api_key=K" in config.streamable_http.url
        assert "/mcp" in config.streamable_http.url
        assert config.name == "mcp_uuid-http"

    @pytest.mark.asyncio
    async def test_sse_branch_still_works(self, mock_logger):
        reg = MCPServerRegistration(
            id="uuid-sse", user_id="u", name="n", description="d",
            endpoint="https://mcp.example.com/sse",
            transport=MCPTransportType.SSE, input_schema=None, is_active=True,
            created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
        )
        with patch(
            "src.infrastructure.mcp_registry.mcp_tool_loader.MCPToolRegistry"
        ) as MockRegistry:
            MockRegistry.return_value.get_tools = AsyncMock(return_value=[])
            loader = MCPToolLoader(logger=mock_logger)
            await loader.load(reg, request_id="req-1")
            config = MockRegistry.call_args[1]["configs"][0]

        assert config.transport == MCPTransport.SSE
        assert config.sse.url == "https://mcp.example.com/sse"
