"""UpdateMCPServerUseCase 도구 자동 동기화 테스트.

Design Ref: mcp-tool-auto-sync §2.0, §6.1
Register와 동일한 예외 분류 계약을 따르며, is_active=false 수정 시
카탈로그 비활성화 경로(원 설계 Q5)가 되살아나는지도 함께 고정한다.
"""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.application.mcp_registry.schemas import UpdateMCPServerRequest
from src.application.mcp_registry.update_mcp_server_use_case import (
    UpdateMCPServerUseCase,
)
from src.application.tool_catalog.sync_outcome import DEFAULT_SYNC_HINT
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType


def _entity(id="srv-1", is_active=True):
    return MCPServerRegistration(
        id=id,
        user_id="u1",
        name="weather",
        description="날씨 조회",
        endpoint="https://mcp.example.com/sse",
        transport=MCPTransportType.SSE,
        input_schema=None,
        is_active=is_active,
        created_at=datetime(2026, 8, 31),
        updated_at=datetime(2026, 8, 31),
    )


def _use_case(sync_uc=None, timeout=10.0, existing=None):
    repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
    repo.find_by_id.return_value = existing if existing is not None else _entity()
    repo.update.side_effect = lambda e, rid: e
    logger = MagicMock()
    kwargs = {"repository": repo, "logger": logger}
    if sync_uc is not None:
        kwargs["sync_use_case"] = sync_uc
        kwargs["sync_timeout_sec"] = timeout
    return UpdateMCPServerUseCase(**kwargs), repo, logger


class TestUpdateToolSyncSuccess:
    @pytest.mark.asyncio
    async def test_sync_called_with_updated_server_id(self):
        """FR-02/FR-04: 수정한 서버 1개만 대상으로 sync한다."""
        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(return_value=2)
        uc, _, _ = _use_case(sync_uc)

        await uc.execute("srv-1", UpdateMCPServerRequest(name="새 이름"), "req-1")

        sync_uc.execute.assert_awaited_once()
        assert sync_uc.execute.await_args.args[0] == "srv-1"

    @pytest.mark.asyncio
    async def test_response_carries_sync_success(self):
        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(return_value=2)
        uc, _, _ = _use_case(sync_uc)

        result = await uc.execute("srv-1", UpdateMCPServerRequest(name="새 이름"), "req-1")

        assert result.tool_sync is not None
        assert result.tool_sync.ok is True
        assert result.tool_sync.synced_count == 2

    @pytest.mark.asyncio
    async def test_deactivation_triggers_sync(self):
        """FR-08: is_active=false 수정도 sync를 호출해 카탈로그 비활성화를 유발한다.

        비활성화 처리 자체는 SyncMcpToolsUseCase.deactivate_by_mcp_server 책임이므로
        여기서는 sync가 호출되는지만 고정한다(원 설계 Q5 복구).
        """
        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(return_value=0)
        uc, _, _ = _use_case(sync_uc)

        result = await uc.execute(
            "srv-1", UpdateMCPServerRequest(is_active=False), "req-1"
        )

        sync_uc.execute.assert_awaited_once_with("srv-1", "req-1")
        assert result.tool_sync.ok is True


class TestUpdateToolSyncSkipped:
    @pytest.mark.asyncio
    async def test_no_sync_dependency_keeps_legacy_behavior(self):
        """FR-06: sync 미주입이면 기존과 동일하게 동작하고 tool_sync는 null."""
        uc, repo, _ = _use_case(sync_uc=None)

        result = await uc.execute("srv-1", UpdateMCPServerRequest(name="새 이름"), "req-1")

        assert result.tool_sync is None
        repo.update.assert_awaited_once()


class TestUpdateToolSyncFailure:
    @pytest.mark.asyncio
    async def test_network_failure_does_not_break_update(self):
        """FR-03: MCP 서버 무응답이어도 수정은 성공한다."""
        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(side_effect=ConnectionError("connection refused"))
        uc, repo, _ = _use_case(sync_uc)

        result = await uc.execute("srv-1", UpdateMCPServerRequest(name="새 이름"), "req-1")

        assert result.id == "srv-1"
        assert result.tool_sync.ok is False
        assert result.tool_sync.error_hint == DEFAULT_SYNC_HINT
        repo.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_network_failure_logs_warning_with_context(self):
        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(side_effect=ConnectionError("boom"))
        uc, _, logger = _use_case(sync_uc)

        await uc.execute("srv-1", UpdateMCPServerRequest(name="새 이름"), "req-1")

        logger.warning.assert_called_once()
        kwargs = logger.warning.call_args.kwargs
        assert kwargs["request_id"] == "req-1"
        assert kwargs["server_id"] == "srv-1"

    @pytest.mark.asyncio
    async def test_timeout_is_swallowed_and_hinted(self):
        async def _never_returns(*_args, **_kwargs):
            await asyncio.sleep(10)

        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(side_effect=_never_returns)
        uc, _, _ = _use_case(sync_uc, timeout=0.01)

        result = await uc.execute("srv-1", UpdateMCPServerRequest(name="새 이름"), "req-1")

        assert result.tool_sync.ok is False
        assert "지연" in result.tool_sync.error_hint


class TestUpdateToolSyncDbError:
    @pytest.mark.asyncio
    async def test_sqlalchemy_error_is_reraised(self):
        """§2.0 핵심 계약: 세션 오염 예외는 재전파한다."""
        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(side_effect=SQLAlchemyError("db is gone"))
        uc, _, _ = _use_case(sync_uc)

        with pytest.raises(SQLAlchemyError):
            await uc.execute("srv-1", UpdateMCPServerRequest(name="새 이름"), "req-1")


class TestUpdateValidationUnaffected:
    @pytest.mark.asyncio
    async def test_missing_server_skips_sync(self):
        """대상 서버가 없으면 수정도 sync도 일어나지 않는다."""
        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(return_value=1)
        repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
        repo.find_by_id.return_value = None
        uc = UpdateMCPServerUseCase(
            repository=repo, logger=MagicMock(), sync_use_case=sync_uc
        )

        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute("nope", UpdateMCPServerRequest(name="새 이름"), "req-1")

        repo.update.assert_not_awaited()
        sync_uc.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_endpoint_skips_sync(self):
        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(return_value=1)
        uc, repo, _ = _use_case(sync_uc)

        with pytest.raises(ValueError, match="Invalid endpoint"):
            await uc.execute(
                "srv-1", UpdateMCPServerRequest(endpoint="not-a-url"), "req-1"
            )

        repo.update.assert_not_awaited()
        sync_uc.execute.assert_not_awaited()
