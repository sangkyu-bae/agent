"""Application 테스트: LoadMCPToolsUseCase."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.tools import BaseTool

from src.application.mcp_registry.load_mcp_tools_use_case import LoadMCPToolsUseCase
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType


def _make_reg(id: str, endpoint: str = "https://a.com/sse"):
    return MCPServerRegistration(
        id=id, user_id="u1", name="T", description="D",
        endpoint=endpoint, transport=MCPTransportType.SSE,
        input_schema=None, is_active=True,
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    )


class TestLoadMCPToolsUseCase:

    @pytest.mark.asyncio
    async def test_execute_returns_all_loaded_tools(self):
        reg1 = _make_reg("a")
        mock_tool = MagicMock(spec=BaseTool)

        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.find_all_active.return_value = [reg1]

        mock_loader = AsyncMock()
        mock_loader.load.return_value = [mock_tool]

        use_case = LoadMCPToolsUseCase(
            repository=mock_repo, mcp_tool_loader=mock_loader, logger=MagicMock()
        )
        tools = await use_case.execute("req-001")

        assert len(tools) == 1
        assert tools[0] is mock_tool

    @pytest.mark.asyncio
    async def test_execute_skips_failed_server_continues_rest(self):
        """하나의 MCP 서버 연결 실패 시 나머지 서버 결과는 반환."""
        reg1 = _make_reg("a")
        reg2 = _make_reg("b")
        mock_tool = MagicMock(spec=BaseTool)

        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.find_all_active.return_value = [reg1, reg2]

        mock_loader = AsyncMock()
        mock_loader.load.side_effect = [
            ConnectionError("refused"),  # reg1 실패
            [mock_tool],                 # reg2 성공
        ]

        use_case = LoadMCPToolsUseCase(
            repository=mock_repo, mcp_tool_loader=mock_loader, logger=MagicMock()
        )
        tools = await use_case.execute("req-001")

        assert len(tools) == 1

    @pytest.mark.asyncio
    async def test_execute_returns_empty_when_no_active_servers(self):
        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.find_all_active.return_value = []

        use_case = LoadMCPToolsUseCase(
            repository=mock_repo, mcp_tool_loader=AsyncMock(), logger=MagicMock()
        )
        tools = await use_case.execute("req-001")

        assert tools == []

    @pytest.mark.asyncio
    async def test_execute_list_meta_returns_registrations(self):
        reg1 = _make_reg("a")

        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.find_all_active.return_value = [reg1]

        use_case = LoadMCPToolsUseCase(
            repository=mock_repo, mcp_tool_loader=AsyncMock(), logger=MagicMock()
        )
        metas = await use_case.list_meta("req-001")

        assert len(metas) == 1
        assert metas[0].tool_id == "mcp_a"
