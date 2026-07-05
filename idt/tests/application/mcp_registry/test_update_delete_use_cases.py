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


def _make_streamable_reg(id="uuid-2", auth_config=None):
    return MCPServerRegistration(
        id=id, user_id="u1", name="S", description="d",
        endpoint="https://server.smithery.ai/@x/y/mcp",
        transport=MCPTransportType.STREAMABLE_HTTP,
        input_schema=None, is_active=True,
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
        auth_config=auth_config,
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

    @pytest.mark.asyncio
    async def test_raises_when_switch_to_streamable_http_without_api_key(self):
        # SSE → streamable_http 전환 시 api_key가 없으면 거부 (404 유발 사전 차단)
        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.find_by_id.return_value = _make_reg()

        use_case = UpdateMCPServerUseCase(repository=mock_repo, logger=MagicMock())
        request = UpdateMCPServerRequest(transport="streamable_http")
        with pytest.raises(ValueError, match="api_key"):
            await use_case.execute("uuid-1", request, "req-001")
        mock_repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_when_auth_config_cleared_to_empty(self):
        # 기존 streamable_http 서버의 api_key를 빈 값으로 갱신하면 거부
        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.find_by_id.return_value = _make_streamable_reg(
            auth_config={"api_key": "K"}
        )

        use_case = UpdateMCPServerUseCase(repository=mock_repo, logger=MagicMock())
        request = UpdateMCPServerRequest(auth_config={"api_key": ""})
        with pytest.raises(ValueError, match="api_key"):
            await use_case.execute("uuid-2", request, "req-001")
        mock_repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_ok_when_streamable_with_valid_key(self):
        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.find_by_id.return_value = _make_reg()
        mock_repo.update.return_value = _make_streamable_reg(
            auth_config={"api_key": "K"}
        )

        use_case = UpdateMCPServerUseCase(repository=mock_repo, logger=MagicMock())
        request = UpdateMCPServerRequest(
            transport="streamable_http", auth_config={"api_key": "K"}
        )
        result = await use_case.execute("uuid-1", request, "req-001")

        assert result.transport == "streamable_http"
        mock_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_switch_to_streamable_http_rejected_when_secrets_disabled(self):
        # MCP_SECRET_KEY 미설정 시 streamable_http 전환을 거부 (silent secret-drop 방지)
        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.find_by_id.return_value = _make_reg()

        use_case = UpdateMCPServerUseCase(
            repository=mock_repo, logger=MagicMock(), secrets_enabled=False
        )
        request = UpdateMCPServerRequest(
            transport="streamable_http", auth_config={"api_key": "K"}
        )
        with pytest.raises(ValueError, match="MCP_SECRET_KEY"):
            await use_case.execute("uuid-1", request, "req-001")
        mock_repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_name_only_update_not_blocked_on_streamable(self):
        # transport/auth를 건드리지 않는 부분 수정은 검증으로 막지 않는다
        existing = _make_streamable_reg(auth_config={"api_key": "K"})
        mock_repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        mock_repo.find_by_id.return_value = existing
        mock_repo.update.return_value = existing

        use_case = UpdateMCPServerUseCase(repository=mock_repo, logger=MagicMock())
        result = await use_case.execute(
            "uuid-2", UpdateMCPServerRequest(name="New"), "req-001"
        )

        assert result is not None
        mock_repo.update.assert_called_once()


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
