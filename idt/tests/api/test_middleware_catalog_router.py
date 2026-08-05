"""Middleware Catalog Router 단위 테스트 — builtin-middleware D4."""
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.middleware.schemas import (
    MiddlewareCatalogItemResponse,
    MiddlewareCatalogListResponse,
)


def _item(**kw) -> MiddlewareCatalogItemResponse:
    defaults = dict(
        middleware_type="model_retry",
        name="LLM 재시도",
        description="지수 백오프 재시도",
        is_builtin=True,
        is_enforced=False,
        default_config={"max_retries": 3},
        is_active=True,
        sort_order=10,
    )
    defaults.update(kw)
    return MiddlewareCatalogItemResponse(**defaults)


def _make_fake_admin():
    from src.domain.auth.entities import User, UserRole, UserStatus
    return User(
        email="admin@test.com", password_hash="hashed",
        role=UserRole.ADMIN, status=UserStatus.APPROVED, id=1,
    )


def _make_fake_user():
    from src.domain.auth.entities import User, UserRole, UserStatus
    return User(
        email="user@test.com", password_hash="hashed",
        role=UserRole.USER, status=UserStatus.APPROVED, id=2,
    )


def _make_client(overrides: dict) -> TestClient:
    from src.api.routes.middleware_catalog_router import router
    from src.interfaces.dependencies.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _make_fake_admin
    for dep, override in overrides.items():
        app.dependency_overrides[dep] = override
    return TestClient(app)


class TestListMiddlewareCatalog:
    def test_list_returns_200(self):
        from src.api.routes.middleware_catalog_router import (
            get_list_middleware_catalog_use_case,
        )
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            return_value=MiddlewareCatalogListResponse(middlewares=[_item()])
        )
        client = _make_client(
            {get_list_middleware_catalog_use_case: lambda: mock_uc}
        )
        resp = client.get("/api/v1/middleware-catalog")
        assert resp.status_code == 200
        body = resp.json()["middlewares"][0]
        assert body["middleware_type"] == "model_retry"
        assert body["is_builtin"] is True
        assert body["default_config"] == {"max_retries": 3}


class TestSetMiddlewareFlags:
    def test_patch_admin_200(self):
        from src.api.routes.middleware_catalog_router import (
            get_set_middleware_flags_use_case,
        )
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=_item(is_enforced=True))
        client = _make_client(
            {get_set_middleware_flags_use_case: lambda: mock_uc}
        )
        resp = client.patch(
            "/api/v1/middleware-catalog/model_retry",
            json={"is_enforced": True},
        )
        assert resp.status_code == 200
        assert resp.json()["is_enforced"] is True

    def test_patch_unknown_type_404(self):
        from src.api.routes.middleware_catalog_router import (
            get_set_middleware_flags_use_case,
        )
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            side_effect=LookupError("Unknown middleware_type: '없는것'")
        )
        client = _make_client(
            {get_set_middleware_flags_use_case: lambda: mock_uc}
        )
        resp = client.patch(
            "/api/v1/middleware-catalog/nope", json={"is_builtin": True}
        )
        assert resp.status_code == 404

    def test_patch_invalid_config_400(self):
        from src.api.routes.middleware_catalog_router import (
            get_set_middleware_flags_use_case,
        )
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            side_effect=ValueError("max_retries must be 0~10")
        )
        client = _make_client(
            {get_set_middleware_flags_use_case: lambda: mock_uc}
        )
        resp = client.patch(
            "/api/v1/middleware-catalog/model_retry",
            json={"default_config": {"max_retries": 99}},
        )
        assert resp.status_code == 400

    def test_patch_non_admin_403(self):
        from src.api.routes.middleware_catalog_router import (
            get_set_middleware_flags_use_case,
        )
        from src.interfaces.dependencies.auth import get_current_user
        mock_uc = MagicMock()
        client = _make_client({
            get_set_middleware_flags_use_case: lambda: mock_uc,
            get_current_user: _make_fake_user,
        })
        resp = client.patch(
            "/api/v1/middleware-catalog/model_retry",
            json={"is_builtin": False},
        )
        assert resp.status_code == 403
        mock_uc.execute.assert_not_called()
