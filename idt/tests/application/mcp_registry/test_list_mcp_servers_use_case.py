"""Application 테스트: ListMCPServersUseCase."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.mcp_registry.list_mcp_servers_use_case import ListMCPServersUseCase
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType


def _make_reg(id="u1", user_id="user-1"):
    return MCPServerRegistration(
        id=id, user_id=user_id, name="T", description="D",
        endpoint="https://a.com/sse", transport=MCPTransportType.SSE,
        input_schema=None, is_active=True,
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    )


class TestListMCPServersUseCaseByUser:

    @pytest.mark.asyncio
    async def test_execute_by_user_returns_items(self):
        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.find_by_user.return_value = [_make_reg()]

        use_case = ListMCPServersUseCase(repository=mock_repo, logger=MagicMock())
        result = await use_case.execute_by_user("user-1", "req-001")

        assert result.total == 1
        assert result.items[0].tool_id == "mcp_u1"
        mock_repo.find_by_user.assert_called_once_with("user-1", "req-001")

    @pytest.mark.asyncio
    async def test_execute_by_user_returns_empty(self):
        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.find_by_user.return_value = []

        use_case = ListMCPServersUseCase(repository=mock_repo, logger=MagicMock())
        result = await use_case.execute_by_user("user-1", "req-001")

        assert result.total == 0
        assert result.items == []


class TestListMCPServersUseCaseAll:

    @pytest.mark.asyncio
    async def test_execute_all_returns_active_items(self):
        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.find_all_active.return_value = [_make_reg("a"), _make_reg("b")]

        use_case = ListMCPServersUseCase(repository=mock_repo, logger=MagicMock())
        result = await use_case.execute_all("req-001")

        assert result.total == 2

    @pytest.mark.asyncio
    async def test_execute_by_id_returns_none_when_not_found(self):
        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.find_by_id.return_value = None

        use_case = ListMCPServersUseCase(repository=mock_repo, logger=MagicMock())
        result = await use_case.execute_by_id("missing", "req-001")

        assert result is None
