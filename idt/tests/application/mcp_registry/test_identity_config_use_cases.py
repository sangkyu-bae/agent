"""MCP 등록/수정 UseCase — identity_config.

Design Ref: mcp-identity-header §4.2. PUT 은 auth_config 와 달리 통째 교체가
아니다: 필드 없음=불변, null=해제, 비밀 없는 객체=기존 비밀 유지.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.mcp_registry.register_mcp_server_use_case import (
    RegisterMCPServerUseCase,
)
from src.application.mcp_registry.schemas import (
    RegisterMCPServerRequest,
    UpdateMCPServerRequest,
)
from src.application.mcp_registry.update_mcp_server_use_case import (
    UpdateMCPServerUseCase,
)
from src.domain.mcp_registry.identity import IdentityHeaderConfig
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType

_OLD = "o" * 32
_NEW = "n" * 32
_IDENTITY = {"audience": "mcp-outlook-server", "secret": _NEW}


def _repo(existing: MCPServerRegistration | None = None):
    repo = AsyncMock(spec=MCPServerRegistryRepositoryInterface)
    repo.find_by_id.return_value = existing
    repo.save.side_effect = lambda reg, _rid: reg
    repo.update.side_effect = lambda reg, _rid: reg
    return repo


def _register_request(**over) -> RegisterMCPServerRequest:
    base = dict(
        user_id="7", name="Outlook", description="메일",
        endpoint="http://localhost:8006/sse", transport="sse",
    )
    base.update(over)
    return RegisterMCPServerRequest(**base)


def _existing(identity: bool = True) -> MCPServerRegistration:
    return MCPServerRegistration(
        id="srv-1", user_id="7", name="Outlook", description="d",
        endpoint="http://localhost:8006/sse", transport=MCPTransportType.SSE,
        input_schema=None, is_active=True,
        created_at=datetime(2026, 9, 1), updated_at=datetime(2026, 9, 1),
        identity_config=(
            IdentityHeaderConfig.from_dict({"audience": "old-aud", "secret": _OLD})
            if identity else None
        ),
    )


class TestRegister:
    @pytest.mark.asyncio
    async def test_신원_설정을_저장하고_응답에서_비밀을_가린다(self):
        repo = _repo()
        uc = RegisterMCPServerUseCase(repository=repo, logger=MagicMock())
        resp = await uc.execute(_register_request(identity_config=_IDENTITY), "r")
        saved = repo.save.call_args.args[0]
        assert saved.identity_config.secret == _NEW
        assert resp.identity_config["secret"] == "****"
        assert resp.identity_config["audience"] == "mcp-outlook-server"
        assert _NEW not in resp.model_dump_json()

    @pytest.mark.asyncio
    async def test_생략하면_신원_미설정(self):
        repo = _repo()
        uc = RegisterMCPServerUseCase(repository=repo, logger=MagicMock())
        resp = await uc.execute(_register_request(), "r")
        assert repo.save.call_args.args[0].identity_config is None
        assert resp.identity_config is None

    @pytest.mark.asyncio
    async def test_암호화_키가_없으면_거부(self):
        uc = RegisterMCPServerUseCase(
            repository=_repo(), logger=MagicMock(), secrets_enabled=False
        )
        with pytest.raises(ValueError, match="MCP_SECRET_KEY"):
            await uc.execute(_register_request(identity_config=_IDENTITY), "r")

    @pytest.mark.asyncio
    async def test_규칙_위반은_ValueError(self):
        uc = RegisterMCPServerUseCase(repository=_repo(), logger=MagicMock())
        with pytest.raises(ValueError):
            await uc.execute(
                _register_request(identity_config={"audience": "a", "secret": "short"}), "r"
            )

    @pytest.mark.asyncio
    async def test_정적_헤더와_이름이_겹치면_거부(self):
        uc = RegisterMCPServerUseCase(repository=_repo(), logger=MagicMock())
        with pytest.raises(ValueError, match="header"):
            await uc.execute(
                _register_request(
                    identity_config=_IDENTITY,
                    auth_config={"headers": {"X-MCP-Identity": "static"}},
                ),
                "r",
            )


class TestUpdate:
    async def _run(self, existing, request, **kwargs):
        repo = _repo(existing)
        uc = UpdateMCPServerUseCase(repository=repo, logger=MagicMock(), **kwargs)
        resp = await uc.execute("srv-1", request, "r")
        return repo.update.call_args.args[0], resp

    @pytest.mark.asyncio
    async def test_필드가_없으면_그대로(self):
        saved, _ = await self._run(_existing(), UpdateMCPServerRequest(name="새 이름"))
        assert saved.identity_config.secret == _OLD
        assert saved.identity_config.audience == "old-aud"

    @pytest.mark.asyncio
    async def test_null이면_해제(self):
        saved, resp = await self._run(
            _existing(), UpdateMCPServerRequest(identity_config=None)
        )
        assert saved.identity_config is None
        assert resp.identity_config is None

    @pytest.mark.asyncio
    async def test_비밀_없이_오면_기존_비밀_유지(self):
        saved, _ = await self._run(
            _existing(), UpdateMCPServerRequest(identity_config={"audience": "new-aud"})
        )
        assert saved.identity_config.secret == _OLD
        assert saved.identity_config.audience == "new-aud"

    @pytest.mark.asyncio
    async def test_비밀이_있으면_교체(self):
        saved, _ = await self._run(
            _existing(), UpdateMCPServerRequest(identity_config=_IDENTITY)
        )
        assert saved.identity_config.secret == _NEW

    @pytest.mark.asyncio
    async def test_기존_설정_없이_비밀도_없으면_거부(self):
        with pytest.raises(ValueError):
            await self._run(
                _existing(identity=False),
                UpdateMCPServerRequest(identity_config={"audience": "a"}),
            )

    @pytest.mark.asyncio
    async def test_암호화_키가_없으면_신원_설정_변경을_거부(self):
        with pytest.raises(ValueError, match="MCP_SECRET_KEY"):
            await self._run(
                _existing(identity=False),
                UpdateMCPServerRequest(identity_config=_IDENTITY),
                secrets_enabled=False,
            )

    @pytest.mark.asyncio
    async def test_정적_헤더_수정이_신원_헤더와_겹치면_거부(self):
        """R-6 — 신원은 그대로 두고 auth_config 만 바꿔도 충돌을 검사한다."""
        with pytest.raises(ValueError, match="header"):
            await self._run(
                _existing(),
                UpdateMCPServerRequest(auth_config={"headers": {"x-mcp-identity": "s"}}),
            )
