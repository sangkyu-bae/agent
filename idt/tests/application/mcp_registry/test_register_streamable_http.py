"""Application 테스트: RegisterMCPServerUseCase streamable_http + 마스킹."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.mcp_registry.register_mcp_server_use_case import (
    RegisterMCPServerUseCase,
)
from src.application.mcp_registry.schemas import RegisterMCPServerRequest
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType


def _echo_save():
    """repo.save가 전달된 엔티티를 그대로 반환하도록 한다."""
    async def _save(entity, request_id):
        return entity
    return _save


class TestRegisterStreamableHttp:

    @pytest.mark.asyncio
    async def test_registers_streamable_http_and_masks_response(self):
        repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        repo.save.side_effect = _echo_save()
        uc = RegisterMCPServerUseCase(repository=repo, logger=MagicMock())

        request = RegisterMCPServerRequest(
            user_id="u1", name="Naver Search", description="d",
            endpoint="https://server.smithery.ai/@isnow890/naver-search-mcp",
            transport="streamable_http",
            auth_config={"api_key": "K", "profile": "P"},
            server_config={"NAVER_CLIENT_ID": "id", "NAVER_CLIENT_SECRET": "sec"},
        )
        result = await uc.execute(request, "req-1")

        # 저장된 엔티티는 평문 보존
        saved = repo.save.call_args[0][0]
        assert saved.transport == MCPTransportType.STREAMABLE_HTTP
        assert saved.auth_config == {"api_key": "K", "profile": "P"}
        # 응답은 마스킹
        assert result.transport == "streamable_http"
        assert result.auth_config == {"api_key": "****", "profile": "****"}
        assert result.server_config == {
            "NAVER_CLIENT_ID": "****",
            "NAVER_CLIENT_SECRET": "****",
        }

    @pytest.mark.asyncio
    async def test_streamable_http_without_api_key_rejected(self):
        uc = RegisterMCPServerUseCase(repository=AsyncMock(), logger=MagicMock())
        request = RegisterMCPServerRequest(
            user_id="u1", name="T", description="d",
            endpoint="https://server.smithery.ai/@x/y",
            transport="streamable_http",
        )
        with pytest.raises(ValueError, match="api_key"):
            await uc.execute(request, "req-1")

    @pytest.mark.asyncio
    async def test_streamable_http_rejected_when_secrets_disabled(self):
        # MCP_SECRET_KEY 미설정(secrets_enabled=False) 시 시크릿이 NULL로 버려지므로 거부
        repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        uc = RegisterMCPServerUseCase(
            repository=repo, logger=MagicMock(), secrets_enabled=False
        )
        request = RegisterMCPServerRequest(
            user_id="u1", name="T", description="d",
            endpoint="https://server.smithery.ai/@x/y",
            transport="streamable_http",
            auth_config={"api_key": "K"},
        )
        with pytest.raises(ValueError, match="MCP_SECRET_KEY"):
            await uc.execute(request, "req-1")
        repo.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_sse_allowed_when_secrets_disabled(self):
        repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        repo.save.side_effect = _echo_save()
        uc = RegisterMCPServerUseCase(
            repository=repo, logger=MagicMock(), secrets_enabled=False
        )
        request = RegisterMCPServerRequest(
            user_id="u1", name="T", description="d",
            endpoint="https://e/sse", transport="sse",
        )
        result = await uc.execute(request, "req-1")
        assert result.transport == "sse"

    @pytest.mark.asyncio
    async def test_invalid_transport_rejected(self):
        uc = RegisterMCPServerUseCase(repository=AsyncMock(), logger=MagicMock())
        request = RegisterMCPServerRequest(
            user_id="u1", name="T", description="d",
            endpoint="https://e/x", transport="grpc",
        )
        with pytest.raises(ValueError, match="Invalid transport"):
            await uc.execute(request, "req-1")
