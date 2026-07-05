"""Application 테스트: TestMCPConnectionUseCase 연결 테스트."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.mcp_registry.mcp_connection_test_use_case import (
    MCPConnectionTestUseCase,
)
from src.domain.mcp.value_objects import MCPToolDescriptor
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType

_CLIENT_PATH = (
    "src.application.mcp_registry.mcp_connection_test_use_case.MCPCallClient"
)


def _registration() -> MCPServerRegistration:
    now = datetime.utcnow()
    return MCPServerRegistration(
        id="srv-1",
        user_id="u1",
        name="Naver",
        description="d",
        endpoint="https://server.smithery.ai/@x/y/mcp",
        transport=MCPTransportType.STREAMABLE_HTTP,
        input_schema=None,
        is_active=True,
        created_at=now,
        updated_at=now,
        auth_config={"api_key": "K"},
        server_config=None,
    )


class TestMCPConnectionTest:

    @pytest.mark.asyncio
    async def test_returns_ok_with_tools_on_success(self):
        repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        repo.find_by_id.return_value = _registration()
        uc = MCPConnectionTestUseCase(repository=repo, logger=MagicMock())

        fake_client = MagicMock()
        fake_client.list_tools = AsyncMock(
            return_value=[
                MCPToolDescriptor(
                    name="search", description="웹 검색", input_schema={}
                ),
            ]
        )
        with patch(_CLIENT_PATH, return_value=fake_client):
            result = await uc.execute("srv-1", "req-1")

        assert result is not None
        assert result.ok is True
        assert result.tools == [{"name": "search", "description": "웹 검색"}]
        assert result.error is None

    @pytest.mark.asyncio
    async def test_returns_not_ok_on_connection_failure(self):
        repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        repo.find_by_id.return_value = _registration()
        logger = MagicMock()
        uc = MCPConnectionTestUseCase(repository=repo, logger=logger)

        fake_client = MagicMock()
        fake_client.list_tools = AsyncMock(
            side_effect=RuntimeError("connection refused")
        )
        with patch(_CLIENT_PATH, return_value=fake_client):
            result = await uc.execute("srv-1", "req-1")

        assert result is not None
        assert result.ok is False
        assert "connection refused" in result.error
        logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_terminated_in_group_returns_diagnostic_hint(self):
        # SDK는 404를 ExceptionGroup으로 감싼 McpError("Session terminated")로 올린다
        repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        repo.find_by_id.return_value = _registration()
        uc = MCPConnectionTestUseCase(repository=repo, logger=MagicMock())

        inner = RuntimeError("Session terminated")
        group = ExceptionGroup("unhandled errors in a TaskGroup", [inner])
        fake_client = MagicMock()
        fake_client.list_tools = AsyncMock(side_effect=group)
        with patch(_CLIENT_PATH, return_value=fake_client):
            result = await uc.execute("srv-1", "req-1")

        assert result.ok is False
        assert "api_key" in result.error
        assert "/mcp" in result.error

    @pytest.mark.asyncio
    async def test_session_terminated_via_cause_chain_returns_hint(self):
        repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        repo.find_by_id.return_value = _registration()
        uc = MCPConnectionTestUseCase(repository=repo, logger=MagicMock())

        try:
            raise RuntimeError("Session terminated")
        except RuntimeError as inner:
            outer = RuntimeError("unhandled errors in a TaskGroup")
            outer.__cause__ = inner
        fake_client = MagicMock()
        fake_client.list_tools = AsyncMock(side_effect=outer)
        with patch(_CLIENT_PATH, return_value=fake_client):
            result = await uc.execute("srv-1", "req-1")

        assert result.ok is False
        assert "api_key" in result.error

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        repo.find_by_id.return_value = None
        uc = MCPConnectionTestUseCase(repository=repo, logger=MagicMock())

        result = await uc.execute("missing", "req-1")

        assert result is None
