"""API 테스트: GET /auth/me 부서 노출 (expose-user-department)."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.auth_router import (
    router,
    get_current_user,
    get_user_departments_use_case,
)
from src.application.department.get_user_departments_use_case import DepartmentBrief
from src.domain.auth.entities import User, UserRole, UserStatus


def _user() -> User:
    return User(
        email="user@example.com", password_hash="hashed",
        role=UserRole.USER, status=UserStatus.APPROVED, id=7,
    )


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    return a


def _client(app, briefs):
    uc = MagicMock()
    uc.execute = AsyncMock(return_value=briefs)
    app.dependency_overrides[get_current_user] = _user
    app.dependency_overrides[get_user_departments_use_case] = lambda: uc
    return TestClient(app)


class TestMeDepartments:
    def test_소속_부서를_포함한다(self, app):
        client = _client(app, [
            DepartmentBrief(id="d1", name="여신심사팀", is_primary=True),
            DepartmentBrief(id="d2", name="여신기획팀", is_primary=False),
        ])

        r = client.get("/api/v1/auth/me")

        assert r.status_code == 200
        body = r.json()
        assert body["id"] == 7
        assert body["email"] == "user@example.com"
        assert len(body["departments"]) == 2
        assert body["departments"][0] == {
            "id": "d1", "name": "여신심사팀", "is_primary": True,
        }

    def test_미소속은_빈_리스트(self, app):
        client = _client(app, [])

        r = client.get("/api/v1/auth/me")

        assert r.status_code == 200
        assert r.json()["departments"] == []

    def test_미인증은_401(self, app):
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=[])
        app.dependency_overrides[get_user_departments_use_case] = lambda: uc
        client = TestClient(app)

        assert client.get("/api/v1/auth/me").status_code == 401
