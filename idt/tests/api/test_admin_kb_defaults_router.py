"""admin_kb_defaults_router + kb_defaults_router L1 — Design §8.2 #1~#5."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes.admin_kb_defaults_router import (
    get_kb_default_setting_use_case,
)
from src.api.routes.admin_kb_defaults_router import (
    router as admin_router,
)
from src.api.routes.kb_defaults_router import router as user_router
from src.application.kb_default_setting.use_case import KbDefaultsView
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.embedding_model.entity import EmbeddingModel
from src.domain.kb_default_setting.entities import KbDefaultSetting
from src.domain.kb_default_setting.errors import (
    EmbeddingModelInactiveError,
    EmbeddingModelNotFoundError,
)
from src.interfaces.dependencies.auth import get_current_user


def _admin() -> User:
    return User(
        email="admin@test.com",
        password_hash="h",
        role=UserRole.ADMIN,
        status=UserStatus.APPROVED,
        id=99,
    )


def _user() -> User:
    return User(
        email="u@test.com",
        password_hash="h",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=1,
    )


def _model() -> EmbeddingModel:
    now = datetime.now(UTC)
    return EmbeddingModel(
        id=2,
        provider="openai",
        model_name="text-embedding-3-small",
        display_name="OpenAI small",
        vector_dimension=1536,
        is_active=True,
        description=None,
        created_at=now,
        updated_at=now,
    )


def _view(configured: bool, warnings: tuple[str, ...] = ()) -> KbDefaultsView:
    return KbDefaultsView(
        setting=KbDefaultSetting(
            default_embedding_model_id=2 if configured else None,
            updated_at=datetime(2026, 11, 5, tzinfo=UTC),
        ),
        model=_model() if configured else None,
        warnings=warnings,
    )


@pytest.fixture
def use_case() -> AsyncMock:
    uc = AsyncMock()
    uc.get.return_value = _view(False)
    uc.update.return_value = _view(True)
    return uc


def _client(use_case: AsyncMock, user: User) -> TestClient:
    app = FastAPI()
    app.include_router(admin_router)
    app.include_router(user_router)
    app.dependency_overrides[get_kb_default_setting_use_case] = lambda: use_case
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


class TestAdminGet:
    def test_unconfigured(self, use_case):
        resp = _client(use_case, _admin()).get("/api/v1/admin/kb-defaults")
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is False
        assert body["model"] is None
        assert body["warnings"] == []

    def test_configured_with_model(self, use_case):
        use_case.get.return_value = _view(True)
        body = _client(use_case, _admin()).get("/api/v1/admin/kb-defaults").json()
        assert body["configured"] is True
        assert body["model"]["id"] == 2
        assert body["model"]["vector_dimension"] == 1536

    def test_non_admin_forbidden(self, use_case):
        resp = _client(use_case, _user()).get("/api/v1/admin/kb-defaults")
        assert resp.status_code == 403


class TestAdminPut:
    def test_sets_model(self, use_case):
        resp = _client(use_case, _admin()).put(
            "/api/v1/admin/kb-defaults", json={"default_embedding_model_id": 2}
        )
        assert resp.status_code == 200
        assert resp.json()["configured"] is True
        use_case.update.assert_awaited_once()
        assert use_case.update.await_args.args[0] == 2

    def test_null_rejected(self, use_case):
        resp = _client(use_case, _admin()).put(
            "/api/v1/admin/kb-defaults", json={"default_embedding_model_id": None}
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "VALIDATION_ERROR"

    def test_unknown_model_404(self, use_case):
        use_case.update.side_effect = EmbeddingModelNotFoundError()
        resp = _client(use_case, _admin()).put(
            "/api/v1/admin/kb-defaults", json={"default_embedding_model_id": 77}
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["code"] == "EMBEDDING_MODEL_NOT_FOUND"

    def test_inactive_model_409(self, use_case):
        use_case.update.side_effect = EmbeddingModelInactiveError()
        resp = _client(use_case, _admin()).put(
            "/api/v1/admin/kb-defaults", json={"default_embedding_model_id": 2}
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "EMBEDDING_MODEL_INACTIVE"


class TestUserGet:
    def test_user_sees_public_summary(self, use_case):
        use_case.get.return_value = _view(True)
        resp = _client(use_case, _user()).get("/api/v1/kb-defaults")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {
            "configured": True,
            "default_embedding_model_id": 2,
            "model_display_name": "OpenAI small",
        }

    def test_user_sees_unconfigured(self, use_case):
        body = _client(use_case, _user()).get("/api/v1/kb-defaults").json()
        assert body["configured"] is False
        assert body["model_display_name"] is None
