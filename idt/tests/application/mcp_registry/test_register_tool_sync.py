"""RegisterMCPServerUseCase 도구 자동 동기화 테스트.

Design Ref: mcp-tool-auto-sync §2.0, §6.1
핵심 계약 — MCP 서버 무응답(네트워크 계열)은 삼켜 등록을 성공시키고,
SQLAlchemyError는 세션을 오염시키므로 재전파한다.
"""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from src.application.mcp_registry.register_mcp_server_use_case import (
    RegisterMCPServerUseCase,
)
from src.application.mcp_registry.schemas import RegisterMCPServerRequest
from src.application.tool_catalog.sync_outcome import DEFAULT_SYNC_HINT
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType


def _saved_entity(id="srv-1"):
    return MCPServerRegistration(
        id=id,
        user_id="u1",
        name="weather",
        description="날씨 조회",
        endpoint="https://mcp.example.com/sse",
        transport=MCPTransportType.SSE,
        input_schema=None,
        is_active=True,
        created_at=datetime(2026, 8, 31),
        updated_at=datetime(2026, 8, 31),
    )


def _request():
    return RegisterMCPServerRequest(
        user_id="u1",
        name="weather",
        description="날씨 조회",
        endpoint="https://mcp.example.com/sse",
    )


def _use_case(sync_uc=None, timeout=10.0):
    repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
    repo.save.return_value = _saved_entity()
    logger = MagicMock()
    kwargs = {"repository": repo, "logger": logger}
    if sync_uc is not None:
        kwargs["sync_use_case"] = sync_uc
        kwargs["sync_timeout_sec"] = timeout
    return RegisterMCPServerUseCase(**kwargs), repo, logger


class TestRegisterToolSyncSuccess:
    @pytest.mark.asyncio
    async def test_sync_called_with_saved_server_id(self):
        """FR-01/FR-04: 방금 저장한 서버 1개만 대상으로 sync한다."""
        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(return_value=3)
        uc, _, _ = _use_case(sync_uc)

        await uc.execute(_request(), "req-1")

        sync_uc.execute.assert_awaited_once()
        assert sync_uc.execute.await_args.args[0] == "srv-1"

    @pytest.mark.asyncio
    async def test_response_carries_sync_success(self):
        """FR-09: 응답 tool_sync에 성공 여부와 동기화 수가 실린다."""
        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(return_value=3)
        uc, _, _ = _use_case(sync_uc)

        result = await uc.execute(_request(), "req-1")

        assert result.tool_sync is not None
        assert result.tool_sync.ok is True
        assert result.tool_sync.synced_count == 3
        assert result.tool_sync.error_hint is None


class TestRegisterToolSyncSkipped:
    @pytest.mark.asyncio
    async def test_no_sync_dependency_keeps_legacy_behavior(self):
        """FR-06: sync 미주입이면 기존과 동일하게 동작하고 tool_sync는 null."""
        uc, repo, _ = _use_case(sync_uc=None)

        result = await uc.execute(_request(), "req-1")

        assert result.id == "srv-1"
        assert result.tool_sync is None
        repo.save.assert_awaited_once()


class TestRegisterToolSyncFailure:
    @pytest.mark.asyncio
    async def test_network_failure_does_not_break_registration(self):
        """FR-03: MCP 서버 무응답이어도 등록은 성공한다."""
        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(side_effect=ConnectionError("connection refused"))
        uc, repo, _ = _use_case(sync_uc)

        result = await uc.execute(_request(), "req-1")

        assert result.id == "srv-1"
        assert result.tool_sync is not None
        assert result.tool_sync.ok is False
        assert result.tool_sync.synced_count == 0
        assert result.tool_sync.error_hint == DEFAULT_SYNC_HINT
        repo.save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_network_failure_logs_warning_with_context(self):
        """관측성: request_id·server_id가 구조화 로그에 남는다."""
        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(side_effect=ConnectionError("boom"))
        uc, _, logger = _use_case(sync_uc)

        await uc.execute(_request(), "req-1")

        logger.warning.assert_called_once()
        kwargs = logger.warning.call_args.kwargs
        assert kwargs["request_id"] == "req-1"
        assert kwargs["server_id"] == "srv-1"
        assert kwargs["error_type"] == "ConnectionError"

    @pytest.mark.asyncio
    async def test_session_terminated_maps_to_api_key_hint(self):
        """TOOL-MCP-001 §3 진단 힌트가 응답에 실린다."""
        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(side_effect=RuntimeError("Session terminated"))
        uc, _, _ = _use_case(sync_uc)

        result = await uc.execute(_request(), "req-1")

        assert "api_key" in result.tool_sync.error_hint

    @pytest.mark.asyncio
    async def test_timeout_is_swallowed_and_hinted(self):
        """R-03: 타임아웃 상한 초과 시 sync만 중단하고 등록은 성공."""

        async def _never_returns(*_args, **_kwargs):
            await asyncio.sleep(10)

        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(side_effect=_never_returns)
        uc, _, _ = _use_case(sync_uc, timeout=0.01)

        result = await uc.execute(_request(), "req-1")

        assert result.id == "srv-1"
        assert result.tool_sync.ok is False
        assert "지연" in result.tool_sync.error_hint


class TestRegisterToolSyncDbError:
    @pytest.mark.asyncio
    async def test_sqlalchemy_error_is_reraised(self):
        """§2.0 핵심 계약: 세션 오염 예외는 삼키면 커밋이 실패하므로 재전파한다."""
        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(side_effect=SQLAlchemyError("db is gone"))
        uc, _, _ = _use_case(sync_uc)

        with pytest.raises(SQLAlchemyError):
            await uc.execute(_request(), "req-1")

    @pytest.mark.asyncio
    async def test_sqlalchemy_subclass_is_reraised(self):
        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(
            side_effect=OperationalError("stmt", {}, Exception("lost connection"))
        )
        uc, _, _ = _use_case(sync_uc)

        with pytest.raises(SQLAlchemyError):
            await uc.execute(_request(), "req-1")

    @pytest.mark.asyncio
    async def test_cancelled_error_is_reraised(self):
        """요청 취소는 흡수하지 않고 전파한다."""
        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(side_effect=asyncio.CancelledError())
        uc, _, _ = _use_case(sync_uc)

        with pytest.raises(asyncio.CancelledError):
            await uc.execute(_request(), "req-1")


class TestRegisterValidationUnaffected:
    @pytest.mark.asyncio
    async def test_validation_failure_skips_sync(self):
        """정책 검증 실패 시 저장도 sync도 일어나지 않는다."""
        sync_uc = MagicMock()
        sync_uc.execute = AsyncMock(return_value=1)
        uc, repo, _ = _use_case(sync_uc)

        bad = RegisterMCPServerRequest(
            user_id="u1", name="T", description="D", endpoint="not-a-url"
        )
        with pytest.raises(ValueError, match="Invalid endpoint"):
            await uc.execute(bad, "req-1")

        repo.save.assert_not_awaited()
        sync_uc.execute.assert_not_awaited()
