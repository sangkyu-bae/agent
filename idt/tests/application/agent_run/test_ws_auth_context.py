"""WsAuthContextResolver 단위 테스트.

fix-ws-auth-context-missing Design §3.1 / §3.4.2 검증:
- 단기 세션 open/close 라이프사이클
- 조립 결과 AuthContext 반환
- UC 예외 전파 (fail-closed는 라우터 책임) + 예외 시에도 세션 close
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_run.ws_auth_context import WsAuthContextResolver
from src.domain.agent_run.auth_context import AuthContext
from src.domain.auth.entities import User, UserRole, UserStatus


def _user(user_id: int = 1) -> User:
    return User(
        email="t@t.com", password_hash="h",
        role=UserRole.USER, status=UserStatus.APPROVED, id=user_id,
    )


def _ctx() -> AuthContext:
    return AuthContext(
        user_id=1,
        display_name="홍길동",
        role="user",
        primary_department_id="d1",
        primary_department_name="여신심사부",
        department_ids=("d1", "d2"),
        department_names=("여신심사부", "리스크부"),
        permissions=frozenset({"USE_RAG_SEARCH"}),
    )


class _FakeSessionCM:
    def __init__(self, session, tracker: dict) -> None:
        self._session = session
        self._tracker = tracker

    async def __aenter__(self):
        self._tracker["entered"] += 1
        return self._session

    async def __aexit__(self, *exc):
        self._tracker["exited"] += 1
        return False


class _FakeSessionFactory:
    def __init__(self) -> None:
        self.tracker = {"entered": 0, "exited": 0}
        self.session = object()

    def __call__(self) -> _FakeSessionCM:
        return _FakeSessionCM(self.session, self.tracker)


def _make_resolver(uc):
    factory = _FakeSessionFactory()
    seen_sessions: list = []

    def _builder(session):
        seen_sessions.append(session)
        return uc

    resolver = WsAuthContextResolver(
        session_factory=factory, assemble_uc_builder=_builder,
    )
    return resolver, factory, seen_sessions


async def test_resolver_opens_and_closes_short_session():
    uc = MagicMock()
    uc.execute = AsyncMock(return_value=_ctx())
    resolver, factory, _ = _make_resolver(uc)

    await resolver.execute(_user(), "req-1")

    assert factory.tracker["entered"] == 1
    assert factory.tracker["exited"] == 1


async def test_resolver_returns_assembled_context_and_uses_session():
    ctx = _ctx()
    uc = MagicMock()
    uc.execute = AsyncMock(return_value=ctx)
    resolver, factory, seen = _make_resolver(uc)

    result = await resolver.execute(_user(7), "req-2")

    assert result is ctx
    # builder는 factory가 연 세션으로 UC를 만든다
    assert seen == [factory.session]
    uc.execute.assert_awaited_once_with(_user(7), "req-2")


async def test_resolver_propagates_exception_and_closes_session():
    uc = MagicMock()
    uc.execute = AsyncMock(side_effect=RuntimeError("db down"))
    resolver, factory, _ = _make_resolver(uc)

    with pytest.raises(RuntimeError, match="db down"):
        await resolver.execute(_user(), "req-3")

    # 예외가 나도 async with 컨텍스트는 정상 종료되어야 함
    assert factory.tracker["exited"] == 1
