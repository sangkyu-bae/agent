"""Auth router integration tests (FastAPI TestClient + dependency_overrides)."""
import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.auth_router import (
    router,
    get_register_use_case,
    get_login_use_case,
    get_refresh_use_case,
    get_logout_use_case,
)
from src.application.auth.register_use_case import RegisterResult
from src.application.auth.login_use_case import LoginResult
from src.application.auth.refresh_token_use_case import RefreshTokenResult


def make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


class TestRegisterEndpoint:
    def test_register_201(self) -> None:
        app = make_app()
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = RegisterResult(
            user_id=1, email="a@b.com", role="user", status="pending"
        )
        app.dependency_overrides[get_register_use_case] = lambda: mock_uc
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "secure1234"})
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending"

    def test_register_409_duplicate(self) -> None:
        app = make_app()
        mock_uc = AsyncMock()
        mock_uc.execute.side_effect = ValueError("Email already registered: a@b.com")
        app.dependency_overrides[get_register_use_case] = lambda: mock_uc
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "secure1234"})
        assert resp.status_code == 409

    def test_register_422_short_password(self) -> None:
        app = make_app()
        mock_uc = AsyncMock()
        app.dependency_overrides[get_register_use_case] = lambda: mock_uc
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/v1/auth/register", json={"email": "a@b.com", "password": "short"})
        assert resp.status_code == 422


class TestLoginEndpoint:
    def test_login_200(self) -> None:
        app = make_app()
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = LoginResult(access_token="acc", refresh_token="ref")
        app.dependency_overrides[get_login_use_case] = lambda: mock_uc
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "pw"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == "acc"
        assert data["token_type"] == "bearer"

    def test_login_401_pending(self) -> None:
        app = make_app()
        mock_uc = AsyncMock()
        mock_uc.execute.side_effect = ValueError("Account is pending approval")
        app.dependency_overrides[get_login_use_case] = lambda: mock_uc
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "pw"})
        assert resp.status_code == 401
        assert "pending" in resp.json()["detail"]

    def test_login_401_invalid_credentials(self) -> None:
        app = make_app()
        mock_uc = AsyncMock()
        mock_uc.execute.side_effect = ValueError("Invalid credentials")
        app.dependency_overrides[get_login_use_case] = lambda: mock_uc
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/v1/auth/login", json={"email": "a@b.com", "password": "wrong"})
        assert resp.status_code == 401


class TestRefreshEndpoint:
    def test_refresh_200(self) -> None:
        app = make_app()
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = RefreshTokenResult(access_token="new_acc")
        app.dependency_overrides[get_refresh_use_case] = lambda: mock_uc
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "rt"})
        assert resp.status_code == 200
        assert resp.json()["access_token"] == "new_acc"

    def test_refresh_401_invalid(self) -> None:
        app = make_app()
        mock_uc = AsyncMock()

        async def _raise(*args, **kwargs):
            raise ValueError("Invalid or expired refresh token")

        mock_uc.execute.side_effect = _raise
        app.dependency_overrides[get_refresh_use_case] = lambda: mock_uc
        client = TestClient(app, raise_server_exceptions=False)

        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "bad"})
        assert resp.status_code == 401
