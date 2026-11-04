"""MCP 레지스트리·레거시 v2 에이전트 라우터 인증 테스트.

Design Ref: tool-access-control §4.1 (Plan FR-16), §0 F5, §8.2 L1-14~16
라우터에 등록된 **모든** 라우트를 순회해 검사한다 — 엔드포인트가 새로 추가돼도
admin 잠금에서 빠지지 않는다는 계약을 고정한다. (app.routes 순회 금지 함정은
include 된 앱 기준이라 여기서는 APIRouter.routes 를 직접 읽는다.)
UseCase 는 대체하지 않는다: 인증이 먼저 막으므로 UseCase 에 도달하면 안 된다.
"""
import re

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from src.api.routes import auto_agent_builder_router, mcp_registry_router, middleware_agent_router
from src.domain.auth.entities import User, UserRole, UserStatus
from src.interfaces.dependencies.auth import get_current_user

ROUTERS = [mcp_registry_router.router, middleware_agent_router.router, auto_agent_builder_router.router]


def _routes():
    for r in ROUTERS:
        for route in r.routes:
            if isinstance(route, APIRoute):
                path = re.sub(r"\{[^}]+\}", "x1", route.path)
                for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                    yield pytest.param(r, method, path, id=f"{method} {route.path}")


def _client(router, user: User | None) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


def _user(role: UserRole) -> User:
    return User(email="u@t", password_hash="h", role=role, status=UserStatus.APPROVED, id=2)


def test_routes_were_collected():
    assert len(list(_routes())) >= 10


@pytest.mark.parametrize("router, method, path", _routes())
def test_unauthenticated_is_401(router, method, path):
    res = _client(router, None).request(method, path, json={})
    assert res.status_code == 401


@pytest.mark.parametrize("router, method, path", _routes())
def test_non_admin_is_403(router, method, path):
    res = _client(router, _user(UserRole.USER)).request(method, path, json={})
    assert res.status_code == 403
