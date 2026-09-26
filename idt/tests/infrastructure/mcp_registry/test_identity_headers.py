"""IdentityHeaderProviderFactory — 서버·주체별 호출 시점 헤더 공급자.

Design Ref: mcp-identity-header §2.1, §2.2, §6.2, §8.2 (#8, #10). 토큰은 공급자를
부를 때마다 새로 만든다 (캐시 금지). 토큰 원문은 어떤 로그에도 남지 않는다.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from jose import jwt as jose_jwt

from src.domain.auth.entities import User, UserStatus
from src.domain.mcp_registry.identity import (
    IdentityHeaderConfig,
    IdentityUnavailableError,
)
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType
from src.infrastructure.mcp_registry.identity_headers import (
    IdentityHeaderProviderFactory,
    SessionScopedUserReader,
)
from src.infrastructure.mcp_registry.identity_token import HmacIdentityTokenSigner

_SECRET = "k" * 40
_NOW = datetime(2026, 9, 26)


def _registration(identity: bool = True) -> MCPServerRegistration:
    cfg = (
        IdentityHeaderConfig.from_dict({"audience": "mcp-outlook-server", "secret": _SECRET})
        if identity else None
    )
    return MCPServerRegistration(
        id="srv-1", user_id="7", name="Outlook", description="d",
        endpoint="http://localhost:8006/sse", transport=MCPTransportType.SSE,
        input_schema=None, is_active=True, created_at=_NOW, updated_at=_NOW,
        identity_config=cfg,
    )


def _user(mailbox: str | None = "kim@corp.com", status=UserStatus.APPROVED) -> User:
    return User(id=7, email="kim@login.local", password_hash="h",
                status=status, mailbox_upn=mailbox)


def _factory(user: User | None = None, clock=None):
    reader = MagicMock()
    reader.find_by_id = AsyncMock(return_value=user)
    logger = MagicMock()
    factory = IdentityHeaderProviderFactory(
        user_reader=reader, signer=HmacIdentityTokenSigner(), logger=logger,
        clock=clock or (lambda: 1000.0),
    )
    return factory, reader, logger


def _decode(token: str) -> dict:
    return jose_jwt.decode(
        token, _SECRET, algorithms=["HS256"], audience="mcp-outlook-server",
        options={"verify_exp": False, "verify_iat": False},
    )


class TestForRegistration:
    def test_신원_미설정_서버는_공급자가_없다(self):
        factory, reader, _ = _factory(_user())
        assert factory.for_registration(_registration(identity=False), "7") is None
        reader.find_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_실행_주체의_메일함으로_토큰을_만든다(self):
        factory, reader, _ = _factory(_user())
        headers = await factory.for_registration(_registration(), "7", "req-1")()
        claims = _decode(headers["X-MCP-Identity"])
        assert claims["sub"] == "7"
        assert claims["preferred_username"] == "kim@corp.com"
        assert (claims["iat"], claims["exp"]) == (1000, 1300)
        reader.find_by_id.assert_awaited_once_with(7)

    @pytest.mark.asyncio
    async def test_호출마다_새로_발급한다(self):
        """R-2 — 로드 시점 고정이면 5분 넘는 실행에서 만료된다."""
        ticks = iter([1000.0, 1500.0])
        factory, reader, _ = _factory(_user(), clock=lambda: next(ticks))
        provide = factory.for_registration(_registration(), "7")
        first = _decode((await provide())["X-MCP-Identity"])
        second = _decode((await provide())["X-MCP-Identity"])
        assert (first["iat"], second["iat"]) == (1000, 1500)
        assert reader.find_by_id.await_count == 2

    @pytest.mark.asyncio
    async def test_발급_로그에_토큰과_비밀이_없다(self):
        factory, _, logger = _factory(_user())
        headers = await factory.for_registration(_registration(), "7", "req-1")()
        logged = str(logger.info.call_args_list)
        assert headers["X-MCP-Identity"] not in logged
        assert _SECRET not in logged
        assert "identity_sub" in logged and "srv-1" in logged


class TestUnavailable:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("subject", [None, ""])
    async def test_주체가_없으면_조회도_하지_않는다(self, subject):
        factory, reader, _ = _factory(_user())
        with pytest.raises(IdentityUnavailableError) as e:
            await factory.for_registration(_registration(), subject)()
        assert e.value.reason == "no_subject"
        reader.find_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_숫자가_아닌_주체는_사용자_없음(self):
        factory, reader, _ = _factory(_user())
        with pytest.raises(IdentityUnavailableError) as e:
            await factory.for_registration(_registration(), "anonymous")()
        assert e.value.reason == "user_not_found"
        reader.find_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_메일함_미등록(self):
        factory, _, _ = _factory(_user(mailbox=None))
        with pytest.raises(IdentityUnavailableError) as e:
            await factory.for_registration(_registration(), "7")()
        assert e.value.reason == "claim_empty"

    @pytest.mark.asyncio
    async def test_비승인_사용자(self):
        factory, _, _ = _factory(_user(status=UserStatus.PENDING))
        with pytest.raises(IdentityUnavailableError) as e:
            await factory.for_registration(_registration(), "7")()
        assert e.value.reason == "user_inactive"


class TestSessionScopedUserReader:
    @pytest.mark.asyncio
    async def test_호출마다_세션을_열어_조회한다(self, monkeypatch):
        session = MagicMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=session)
        cm.__aexit__ = AsyncMock(return_value=None)
        session_factory = MagicMock(return_value=cm)
        found = _user()
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=found)
        repo_cls = MagicMock(return_value=repo)
        monkeypatch.setattr(
            "src.infrastructure.mcp_registry.identity_headers.UserRepository", repo_cls
        )
        reader = SessionScopedUserReader(session_factory=session_factory, logger=MagicMock())
        assert await reader.find_by_id(7) is found
        assert repo_cls.call_args.kwargs["session"] is session
        repo.find_by_id.assert_awaited_once_with(7)
