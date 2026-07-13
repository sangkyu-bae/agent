from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.admin_chunking_router import (
    get_chunking_profile_use_case,
    router,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.chunking_profile.entities import BoundaryRule, ChunkingProfile
from src.interfaces.dependencies.auth import get_current_user


def _user(role: UserRole) -> User:
    return User(
        id=1, email="a@b.c", password_hash="h",
        role=role, status=UserStatus.APPROVED,
    )


def _profile():
    return ChunkingProfile(
        id="p1", name="법령",
        boundary_rules=[
            BoundaryRule(pattern="^제[0-9]+조", priority=1, level="parent"),
            BoundaryRule(pattern="^[ ]*[0-9]+[.]", priority=1, level="child"),
        ],
    )


@pytest.fixture
def mock_use_case() -> AsyncMock:
    uc = AsyncMock()
    uc.create.return_value = _profile()
    uc.get.return_value = _profile()
    uc.list_active.return_value = [_profile()]
    return uc


def _client(mock_use_case: AsyncMock, user: User) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_chunking_profile_use_case] = lambda: mock_use_case
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


_BODY = {
    "name": "법령",
    "boundary_rules": [
        {"pattern": "^제[0-9]+조", "priority": 1, "level": "parent"},
        {"pattern": "^[ ]*[0-9]+[.]", "priority": 1, "level": "child"},
    ],
}


class TestAdminGuard:
    def test_regular_user_403(self, mock_use_case):
        client = _client(mock_use_case, _user(UserRole.USER))
        resp = client.post("/api/v1/admin/chunking/profiles", json=_BODY)
        assert resp.status_code == 403
        mock_use_case.create.assert_not_awaited()

    def test_admin_201(self, mock_use_case):
        client = _client(mock_use_case, _user(UserRole.ADMIN))
        resp = client.post("/api/v1/admin/chunking/profiles", json=_BODY)
        assert resp.status_code == 201
        assert resp.json()["profile_id"] == "p1"


class TestCrudStatusCodes:
    def test_duplicate_409(self, mock_use_case):
        mock_use_case.create.side_effect = ValueError("already exists")
        client = _client(mock_use_case, _user(UserRole.ADMIN))
        resp = client.post("/api/v1/admin/chunking/profiles", json=_BODY)
        assert resp.status_code == 409

    def test_invalid_422(self, mock_use_case):
        mock_use_case.create.side_effect = ValueError("invalid regex pattern")
        client = _client(mock_use_case, _user(UserRole.ADMIN))
        resp = client.post("/api/v1/admin/chunking/profiles", json=_BODY)
        assert resp.status_code == 422

    def test_get_not_found_404(self, mock_use_case):
        mock_use_case.get.side_effect = ValueError("not found")
        client = _client(mock_use_case, _user(UserRole.ADMIN))
        resp = client.get("/api/v1/admin/chunking/profiles/x")
        assert resp.status_code == 404

    def test_delete_default_422(self, mock_use_case):
        mock_use_case.delete.side_effect = ValueError(
            "default profile cannot be deleted"
        )
        client = _client(mock_use_case, _user(UserRole.ADMIN))
        resp = client.delete("/api/v1/admin/chunking/profiles/p1")
        assert resp.status_code == 422

    def test_set_default_ok(self, mock_use_case):
        client = _client(mock_use_case, _user(UserRole.ADMIN))
        resp = client.put("/api/v1/admin/chunking/profiles/p1/default")
        assert resp.status_code == 200
        mock_use_case.set_default.assert_awaited_once()

    def test_list_ok(self, mock_use_case):
        client = _client(mock_use_case, _user(UserRole.ADMIN))
        resp = client.get("/api/v1/admin/chunking/profiles")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
