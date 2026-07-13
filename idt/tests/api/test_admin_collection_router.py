from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.api.routes.admin_collection_router import router
from src.api.routes.collection_router import get_collection_use_case
from src.domain.auth.entities import User, UserRole, UserStatus
from src.interfaces.dependencies.auth import get_current_user


def _user(role: UserRole) -> User:
    return User(
        id=1,
        email="test@example.com",
        password_hash="hashed",
        role=role,
        status=UserStatus.APPROVED,
    )


@pytest.fixture
def mock_use_case() -> AsyncMock:
    return AsyncMock()


def _client(mock_use_case: AsyncMock, user: User) -> TestClient:
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_collection_use_case] = lambda: mock_use_case
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


class TestAdminCreateCollection:
    def test_admin_returns_201(self, mock_use_case: AsyncMock):
        client = _client(mock_use_case, _user(UserRole.ADMIN))
        resp = client.post(
            "/api/v1/admin/collections",
            json={"name": "shared-col", "vector_size": 1536},
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "shared-col"
        mock_use_case.create_collection.assert_awaited_once()

    def test_regular_user_returns_403(self, mock_use_case: AsyncMock):
        client = _client(mock_use_case, _user(UserRole.USER))
        resp = client.post(
            "/api/v1/admin/collections",
            json={"name": "shared-col", "vector_size": 1536},
        )
        assert resp.status_code == 403
        mock_use_case.create_collection.assert_not_awaited()

    def test_default_scope_is_public(self, mock_use_case: AsyncMock):
        client = _client(mock_use_case, _user(UserRole.ADMIN))
        resp = client.post(
            "/api/v1/admin/collections",
            json={"name": "shared-col", "vector_size": 1536},
        )
        assert resp.status_code == 201
        _, kwargs = mock_use_case.create_collection.call_args
        assert kwargs["scope"].value == "PUBLIC"

    def test_duplicate_returns_409(self, mock_use_case: AsyncMock):
        mock_use_case.create_collection.side_effect = ValueError("already exists")
        client = _client(mock_use_case, _user(UserRole.ADMIN))
        resp = client.post(
            "/api/v1/admin/collections",
            json={"name": "dup", "vector_size": 1536},
        )
        assert resp.status_code == 409
