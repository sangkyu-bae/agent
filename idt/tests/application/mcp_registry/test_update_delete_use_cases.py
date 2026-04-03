"""Application 테스트: UpdateMCPServerUseCase, DeleteMCPServerUseCase."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.mcp_registry.schemas import UpdateMCPServerRequest
from src.application.mcp_registry.update_mcp_server_use_case import UpdateMCPServerUseCase
from src.application.mcp_registry.delete_mcp_server_use_case import DeleteMCPServerUseCase
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType


def _make_reg(id="uuid-1"):
    return MCPServerRegistration(
        id=id, user_id="u1", name="Old Name", description="Old Desc",
        endpoint="https://old.com/sse", transport=MCPTransportType.SSE,
        input_schema=None, is_active=True,
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    )


class TestUpdateMCPServerUseCase:

    @pytest.mark.asyncio
    async def test_execute_updates_name(self):
        existing = _make_reg()
        updated = _make_reg()
        updated.name = "New Name"

        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.find_by_id.return_value = existing
        mock_repo.update.return_value = updated

        use_case = UpdateMCPServerUseCase(repository=mock_repo, logger=MagicMock())
        request = UpdateMCPServerRequest(name="New Name")
        result = await use_case.execute("uuid-1", request, "req-001")

        assert result.name == "New Name"
        mock_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_raises_when_not_found(self):
        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.find_by_id.return_value = None

        use_case = UpdateMCPServerUseCase(repository=mock_repo, logger=MagicMock())
        with pytest.raises(ValueError, match="찾을 수 없"):
            await use_case.execute("missing", UpdateMCPServerRequest(), "req-001")

    @pytest.mark.asyncio
    async def test_execute_raises_on_invalid_endpoint(self):
        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.find_by_id.return_value = _make_reg()

        use_case = UpdateMCPServerUseCase(repository=mock_repo, logger=MagicMock())
        request = UpdateMCPServerRequest(endpoint="not-a-url")
        with pytest.raises(ValueError, match="Invalid endpoint"):
            await use_case.execute("uuid-1", request, "req-001")


class TestDeleteMCPServerUseCase:

    @pytest.mark.asyncio
    async def test_execute_returns_true_on_success(self):
        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.delete.return_value = True

        use_case = DeleteMCPServerUseCase(repository=mock_repo, logger=MagicMock())
        result = await use_case.execute("uuid-1", "req-001")

        assert result is True

    @pytest.mark.asyncio
    async def test_execute_returns_false_when_not_found(self):
        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.delete.return_value = False

        use_case = DeleteMCPServerUseCase(repository=mock_repo, logger=MagicMock())
        result = await use_case.execute("missing", "req-001")

        assert result is False
