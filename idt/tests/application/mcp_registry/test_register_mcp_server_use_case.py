"""Application 테스트: RegisterMCPServerUseCase."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.mcp_registry.schemas import RegisterMCPServerRequest
from src.application.mcp_registry.register_mcp_server_use_case import RegisterMCPServerUseCase
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType


def _make_saved_entity(name="My Tool", id="new-uuid"):
    return MCPServerRegistration(
        id=id,
        user_id="u1",
        name=name,
        description="A tool",
        endpoint="https://mcp.example.com/sse",
        transport=MCPTransportType.SSE,
        input_schema=None,
        is_active=True,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


class TestRegisterMCPServerUseCase:

    @pytest.mark.asyncio
    async def test_execute_saves_and_returns_response(self):
        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.save.return_value = _make_saved_entity()

        use_case = RegisterMCPServerUseCase(repository=mock_repo, logger=MagicMock())
        request = RegisterMCPServerRequest(
            user_id="u1",
            name="My Tool",
            description="A tool",
            endpoint="https://mcp.example.com/sse",
        )
        result = await use_case.execute(request, "req-001")

        assert result.tool_id == "mcp_new-uuid"
        assert result.transport == "sse"
        mock_repo.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_raises_on_invalid_endpoint(self):
        use_case = RegisterMCPServerUseCase(
            repository=AsyncMock(), logger=MagicMock()
        )
        request = RegisterMCPServerRequest(
            user_id="u1", name="T", description="D", endpoint="not-a-url"
        )
        with pytest.raises(ValueError, match="Invalid endpoint"):
            await use_case.execute(request, "req-001")

    @pytest.mark.asyncio
    async def test_execute_raises_on_empty_name(self):
        use_case = RegisterMCPServerUseCase(
            repository=AsyncMock(), logger=MagicMock()
        )
        request = RegisterMCPServerRequest(
            user_id="u1", name="   ", description="D",
            endpoint="https://mcp.example.com/sse",
        )
        with pytest.raises(ValueError, match="Invalid name"):
            await use_case.execute(request, "req-001")

    @pytest.mark.asyncio
    async def test_execute_sets_transport_to_sse(self):
        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.save.return_value = _make_saved_entity()

        use_case = RegisterMCPServerUseCase(repository=mock_repo, logger=MagicMock())
        request = RegisterMCPServerRequest(
            user_id="u1", name="T", description="D",
            endpoint="https://mcp.example.com/sse",
        )
        await use_case.execute(request, "req-001")

        saved_entity = mock_repo.save.call_args[0][0]
        assert saved_entity.transport == MCPTransportType.SSE
