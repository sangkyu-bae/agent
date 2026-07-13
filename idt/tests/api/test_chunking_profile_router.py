from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.admin_chunking_router import get_chunking_profile_use_case
from src.api.routes.chunking_profile_router import router
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.chunking_profile.entities import BoundaryRule, ChunkingProfile
from src.interfaces.dependencies.auth import get_current_user


def _user() -> User:
    return User(
        id=1, email="a@b.c", password_hash="h",
        role=UserRole.USER, status=UserStatus.APPROVED,
    )


def _profile(is_default=True):
    return ChunkingProfile(
        id="p1", name="법령",
        boundary_rules=[
            BoundaryRule(pattern="^제[0-9]+조", priority=1, level="parent"),
        ],
        is_default=is_default,
    )


@pytest.fixture
def mock_use_case() -> AsyncMock:
    uc = AsyncMock()
    uc.list_active.return_value = [_profile()]
    return uc


def _client(mock_use_case: AsyncMock) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_chunking_profile_use_case] = lambda: mock_use_case
    app.dependency_overrides[get_current_user] = lambda: _user()
    return TestClient(app)


class TestUserList:
    def test_authenticated_user_lists_profiles(self, mock_use_case):
        client = _client(mock_use_case)
        resp = client.get("/api/v1/chunking/profiles")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["profiles"][0]["is_default"] is True
