"""Admin router integration tests (FastAPI TestClient + dependency_overrides)."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.admin_router import (
    router,
    get_pending_users_use_case,
    get_approve_use_case,
    get_reject_use_case,
)
from src.interfaces.dependencies.auth import get_current_user, require_role
from src.application.auth.get_pending_users_use_case import PendingUserResult
from src.domain.auth.entities import User, UserRole, UserStatus


def _make_admin_user() -> User:
    return User(id=1, email="admin@example.com", password_hash="h", role=UserRole.ADMIN, status=UserStatus.APPROVED)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    # require_role("admin") 내부에서 get_current_user를 호출하므로 둘 다 override
    admin_user = _make_admin_user()
    app.dependency_overrides[get_current_user] = lambda: admin_user
    return app


class TestListPendingUsersEndpoint:
    def test_list_pending_200(self) -> None:
        app = _make_app()
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = [
            PendingUserResult(
                id=2,
                email="pending@example.com",
                role="user",
                created_at=datetime.now(timezone.utc),
            )
        ]
        app.dependency_overrides[get_pending_users_use_case] = lambda: mock_uc
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.get("/api/v1/admin/users/pending")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["email"] == "pending@example.com"
        assert data[0]["role"] == "user"

    def test_list_pending_empty_200(self) -> None:
        app = _make_app()
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = []
        app.dependency_overrides[get_pending_users_use_case] = lambda: mock_uc
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.get("/api/v1/admin/users/pending")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_pending_403_without_admin(self) -> None:
        app = FastAPI()
        app.include_router(router)
        # non-admin user
        normal_user = User(id=99, email="user@example.com", password_hash="h", role=UserRole.USER, status=UserStatus.APPROVED)
        app.dependency_overrides[get_current_user] = lambda: normal_user
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = []
        app.dependency_overrides[get_pending_users_use_case] = lambda: mock_uc
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.get("/api/v1/admin/users/pending")

        assert resp.status_code == 403


class TestApproveUserEndpoint:
    def test_approve_204(self) -> None:
        app = _make_app()
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = None
        app.dependency_overrides[get_approve_use_case] = lambda: mock_uc
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/v1/admin/users/5/approve")

        assert resp.status_code == 204
        mock_uc.execute.assert_awaited_once()

    def test_approve_404_user_not_found(self) -> None:
        app = _make_app()
        mock_uc = AsyncMock()
        mock_uc.execute.side_effect = ValueError("User not found")
        app.dependency_overrides[get_approve_use_case] = lambda: mock_uc
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/v1/admin/users/999/approve")

        assert resp.status_code == 404
        assert "User not found" in resp.json()["detail"]

    def test_approve_403_without_admin(self) -> None:
        app = FastAPI()
        app.include_router(router)
        normal_user = User(id=99, email="user@example.com", password_hash="h", role=UserRole.USER, status=UserStatus.APPROVED)
        app.dependency_overrides[get_current_user] = lambda: normal_user
        mock_uc = AsyncMock()
        app.dependency_overrides[get_approve_use_case] = lambda: mock_uc
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/v1/admin/users/5/approve")

        assert resp.status_code == 403


class TestRejectUserEndpoint:
    def test_reject_204(self) -> None:
        app = _make_app()
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = None
        app.dependency_overrides[get_reject_use_case] = lambda: mock_uc
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/v1/admin/users/6/reject")

        assert resp.status_code == 204
        mock_uc.execute.assert_awaited_once()

    def test_reject_404_user_not_found(self) -> None:
        app = _make_app()
        mock_uc = AsyncMock()
        mock_uc.execute.side_effect = ValueError("User not found")
        app.dependency_overrides[get_reject_use_case] = lambda: mock_uc
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/v1/admin/users/999/reject")

        assert resp.status_code == 404

    def test_reject_403_without_admin(self) -> None:
        app = FastAPI()
        app.include_router(router)
        normal_user = User(id=99, email="user@example.com", password_hash="h", role=UserRole.USER, status=UserStatus.APPROVED)
        app.dependency_overrides[get_current_user] = lambda: normal_user
        mock_uc = AsyncMock()
        app.dependency_overrides[get_reject_use_case] = lambda: mock_uc
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/v1/admin/users/6/reject")

        assert resp.status_code == 403
