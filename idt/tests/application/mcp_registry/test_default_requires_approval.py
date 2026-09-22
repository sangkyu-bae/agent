"""MCP 서버 등록의 default_requires_approval 필드 왕복.

Design Ref: approval-gate-phase2-mcp-executor §3.1, §4.2, §8.3 (A1~A6).
요청 스키마 → UseCase → 엔티티 → 응답까지 값이 끊기지 않는지 고정한다.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from src.application.mcp_registry.register_mcp_server_use_case import (
    RegisterMCPServerUseCase,
)
from src.application.mcp_registry.schemas import (
    RegisterMCPServerRequest,
    UpdateMCPServerRequest,
    to_response,
)
from src.application.mcp_registry.update_mcp_server_use_case import (
    UpdateMCPServerUseCase,
)
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType

_NOW = datetime(2026, 9, 21)


def _entity(**over) -> MCPServerRegistration:
    base = dict(
        id="uuid-1", user_id="u1", name="My Mail", description="메일 서버",
        endpoint="https://mail.example.com/sse", transport=MCPTransportType.SSE,
        input_schema=None, is_active=True, created_at=_NOW, updated_at=_NOW,
    )
    base.update(over)
    return MCPServerRegistration(**base)


def _register_request(**over) -> RegisterMCPServerRequest:
    base = dict(
        user_id="u1", name="My Mail", description="메일 서버",
        endpoint="https://mail.example.com/sse",
    )
    base.update(over)
    return RegisterMCPServerRequest(**base)


def _echo_repo() -> AsyncMock:
    """저장한 엔티티를 그대로 돌려준다 — UseCase 가 실은 값을 관찰하기 위해."""
    repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
    repo.save.side_effect = lambda entity, request_id: entity
    repo.update.side_effect = lambda entity, request_id: entity
    return repo


class TestDomainEntity:
    def test_기본값은_False(self):
        assert _entity().default_requires_approval is False

    def test_apply_update로_바꾼다(self):
        entity = _entity()
        entity.apply_update(
            name=None, description=None, endpoint=None, input_schema=None,
            is_active=None, updated_at=_NOW, default_requires_approval=True,
        )
        assert entity.default_requires_approval is True

    def test_apply_update에서_None은_미변경(self):
        entity = _entity(default_requires_approval=True)
        entity.apply_update(
            name="새 이름", description=None, endpoint=None, input_schema=None,
            is_active=None, updated_at=_NOW,
        )
        assert entity.default_requires_approval is True


class TestRequestSchemas:
    def test_등록_요청은_생략_시_False(self):
        """하위 호환 — 기존 클라이언트는 이 필드를 보내지 않는다."""
        assert _register_request().default_requires_approval is False

    def test_수정_요청은_생략_시_None(self):
        assert UpdateMCPServerRequest().default_requires_approval is None

    def test_bool이_아니면_거부한다(self):
        with pytest.raises(ValidationError):
            _register_request(default_requires_approval={})


class TestRegister:
    async def test_요청값이_엔티티와_응답에_실린다(self):
        repo = _echo_repo()
        uc = RegisterMCPServerUseCase(repository=repo, logger=MagicMock())
        response = await uc.execute(
            _register_request(default_requires_approval=True), "req-1"
        )
        assert repo.save.await_args.args[0].default_requires_approval is True
        assert response.default_requires_approval is True

    async def test_생략하면_False로_저장된다(self):
        repo = _echo_repo()
        uc = RegisterMCPServerUseCase(repository=repo, logger=MagicMock())
        response = await uc.execute(_register_request(), "req-1")
        assert repo.save.await_args.args[0].default_requires_approval is False
        assert response.default_requires_approval is False


class TestUpdate:
    async def test_플래그만_바꿔도_다른_필드는_그대로다(self):
        repo = _echo_repo()
        repo.find_by_id.return_value = _entity()
        uc = UpdateMCPServerUseCase(repository=repo, logger=MagicMock())
        response = await uc.execute(
            "uuid-1", UpdateMCPServerRequest(default_requires_approval=True), "req-1"
        )
        assert response.default_requires_approval is True
        assert response.name == "My Mail"
        assert response.is_active is True

    async def test_생략하면_기존_값을_유지한다(self):
        repo = _echo_repo()
        repo.find_by_id.return_value = _entity(default_requires_approval=True)
        uc = UpdateMCPServerUseCase(repository=repo, logger=MagicMock())
        response = await uc.execute(
            "uuid-1", UpdateMCPServerRequest(name="새 이름"), "req-1"
        )
        assert response.default_requires_approval is True
        assert response.name == "새 이름"


class TestResponse:
    def test_조회_응답에_필드가_있다(self):
        assert to_response(_entity()).default_requires_approval is False
        assert (
            to_response(_entity(default_requires_approval=True))
            .default_requires_approval
            is True
        )
