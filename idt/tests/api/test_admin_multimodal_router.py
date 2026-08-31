"""admin_multimodal_router L1 — Design §4.2 / §8.2 #1~#9."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from src.api.routes.admin_multimodal_router import (
    get_multimodal_settings_use_case,
    router,
)
from src.application.multimodal.settings_use_case import (
    ConnectionTestResult,
    SettingsView,
    VisionModelNotCapableError,
    VisionModelNotFoundError,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.llm_model.entity import LlmModel
from src.domain.multimodal.errors import (
    MultimodalNotConfiguredError,
    UnsupportedVisionProviderError,
)
from src.domain.multimodal.schemas import DescriptionDraft
from src.domain.multimodal.value_objects import MultimodalSettings
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


def _settings(**over) -> MultimodalSettings:
    base = dict(
        id="b0000000-0000-4000-8000-000000000001",
        enabled=True,
        vision_model_id="m1",
        max_images_per_doc=50,
        min_image_px=100,
        min_area_ratio=0.02,
        concurrency=4,
        timeout_sec=60,
        output_language="ko",
        detail_level="detailed",
        updated_at=datetime(2026, 8, 21, 9, 0, tzinfo=UTC),
    )
    base.update(over)
    return MultimodalSettings(**base)


def _llm() -> LlmModel:
    now = datetime.now(UTC)
    return LlmModel(
        id="m1",
        provider="openai",
        model_name="gpt-4o",
        display_name="GPT-4o",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=None,
        is_active=True,
        is_default=False,
        created_at=now,
        updated_at=now,
        supports_vision=True,
    )


def _view(**over) -> SettingsView:
    return SettingsView(settings=_settings(**over), vision_model=_llm(), warnings=())


def _client(uc: AsyncMock, user: User | None = _admin()) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_multimodal_settings_use_case] = lambda: uc
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    else:

        def _unauth():
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no token")

        app.dependency_overrides[get_current_user] = _unauth
    return TestClient(app)


def _put_body(**over) -> dict:
    base = dict(
        enabled=True,
        vision_model_id="m1",
        max_images_per_doc=50,
        min_image_px=100,
        min_area_ratio=0.02,
        concurrency=4,
        timeout_sec=60,
        output_language="ko",
        detail_level="detailed",
    )
    base.update(over)
    return base


BASE = "/api/v1/admin/multimodal"


# ── GET ────────────────────────────────────────────────────────────────────────


def test_get_settings_admin_ok():
    uc = AsyncMock()
    uc.get.return_value = _view()
    r = _client(uc).get(f"{BASE}/settings")
    assert r.status_code == 200
    b = r.json()
    assert b["vision_model_id"] == "m1" and b["enabled"] is True
    assert b["vision_model"]["model_name"] == "gpt-4o"
    assert b["vision_model"]["supports_vision"] is True
    assert b["warnings"] == [] and b["min_area_ratio"] == 0.02
    assert set(b) >= {
        "id",
        "max_images_per_doc",
        "min_image_px",
        "concurrency",
        "timeout_sec",
        "output_language",
        "detail_level",
        "updated_at",
    }


def test_get_settings_surfaces_warnings_and_null_model():
    uc = AsyncMock()
    uc.get.return_value = SettingsView(
        settings=_settings(vision_model_id="gone"),
        vision_model=None,
        warnings=("selected model 'gone' not found",),
    )
    b = _client(uc).get(f"{BASE}/settings").json()
    assert b["vision_model"] is None and b["warnings"] == [
        "selected model 'gone' not found"
    ]


def test_get_settings_user_forbidden():
    r = _client(AsyncMock(), user=_user()).get(f"{BASE}/settings")
    assert r.status_code == 403


def test_get_settings_unauthenticated():
    r = _client(AsyncMock(), user=None).get(f"{BASE}/settings")
    assert r.status_code == 401


# ── PUT ────────────────────────────────────────────────────────────────────────


def test_put_settings_replaces_all_fields():
    uc = AsyncMock()
    uc.update.return_value = _view(concurrency=2)
    r = _client(uc).put(f"{BASE}/settings", json=_put_body(concurrency=2))
    assert r.status_code == 200 and r.json()["concurrency"] == 2
    upd = uc.update.call_args.args[0]
    assert upd.concurrency == 2 and upd.vision_model_id == "m1"


def test_put_settings_out_of_range_400():
    r = _client(AsyncMock()).put(f"{BASE}/settings", json=_put_body(concurrency=0))
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_put_settings_missing_field_400():
    body = _put_body()
    del body["timeout_sec"]
    r = _client(AsyncMock()).put(f"{BASE}/settings", json=body)
    assert r.status_code == 400


def test_put_settings_domain_value_error_400():
    uc = AsyncMock()
    uc.update.side_effect = ValueError(
        "detail_level must be one of ('brief', 'detailed')"
    )
    r = _client(uc).put(f"{BASE}/settings", json=_put_body())
    assert r.status_code == 400 and r.json()["detail"]["code"] == "VALIDATION_ERROR"


def test_put_settings_not_capable_409():
    uc = AsyncMock()
    uc.update.side_effect = VisionModelNotCapableError("inactive")
    r = _client(uc).put(f"{BASE}/settings", json=_put_body())
    assert (
        r.status_code == 409
        and r.json()["detail"]["code"] == "VISION_MODEL_NOT_CAPABLE"
    )


def test_put_settings_not_found_404():
    uc = AsyncMock()
    uc.update.side_effect = VisionModelNotFoundError("nope")
    r = _client(uc).put(f"{BASE}/settings", json=_put_body(vision_model_id="nope"))
    assert (
        r.status_code == 404 and r.json()["detail"]["code"] == "VISION_MODEL_NOT_FOUND"
    )


def test_put_settings_user_forbidden():
    r = _client(AsyncMock(), user=_user()).put(f"{BASE}/settings", json=_put_body())
    assert r.status_code == 403


# ── POST test ──────────────────────────────────────────────────────────────────


def _draft() -> DescriptionDraft:
    return DescriptionDraft(
        detected_type="chart",
        description="막대",
        keywords=["차트"],
        markdown_table=None,
        chart=None,
        page_text=None,
    )


def test_connection_test_without_image_uses_sample():
    uc = AsyncMock()
    uc.test_connection.return_value = ConnectionTestResult(
        ok=True,
        provider="openai",
        model_name="gpt-4o",
        elapsed_ms=120,
        degraded_output_mode=False,
        draft=_draft(),
        error=None,
    )
    r = _client(uc).post(f"{BASE}/test")
    assert r.status_code == 200
    b = r.json()
    assert b["ok"] is True and b["draft"]["detected_type"] == "chart"
    assert uc.test_connection.call_args.args[0] is None


def test_connection_test_with_uploaded_image():
    uc = AsyncMock()
    uc.test_connection.return_value = ConnectionTestResult(
        ok=True,
        provider="openai",
        model_name="gpt-4o",
        elapsed_ms=1,
        degraded_output_mode=True,
        draft=_draft(),
        error=None,
    )
    r = _client(uc).post(
        f"{BASE}/test", files={"image": ("c.png", b"\x89PNGxxxx", "image/png")}
    )
    assert r.status_code == 200 and r.json()["degraded_output_mode"] is True
    args = uc.test_connection.call_args.args
    assert args[0] == b"\x89PNGxxxx" and args[1] == "image/png"


def test_connection_test_rejects_non_image_415():
    r = _client(AsyncMock()).post(
        f"{BASE}/test", files={"image": ("a.pdf", b"%PDF", "application/pdf")}
    )
    assert r.status_code == 415 and r.json()["detail"]["code"] == "UNSUPPORTED_MEDIA"


def test_connection_test_not_configured_409():
    uc = AsyncMock()
    uc.test_connection.side_effect = MultimodalNotConfiguredError(
        "vision_model_id is not set"
    )
    r = _client(uc).post(f"{BASE}/test")
    assert (
        r.status_code == 409
        and r.json()["detail"]["code"] == "MULTIMODAL_NOT_CONFIGURED"
    )


def test_connection_test_provider_failure_is_200_ok_false():
    uc = AsyncMock()
    uc.test_connection.return_value = ConnectionTestResult(
        ok=False,
        provider="openai",
        model_name="gpt-4o",
        elapsed_ms=5,
        degraded_output_mode=False,
        draft=None,
        error="RuntimeError: down",
    )
    r = _client(uc).post(f"{BASE}/test")
    assert (
        r.status_code == 200 and r.json()["ok"] is False and "down" in r.json()["error"]
    )


def test_di_placeholder_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        get_multimodal_settings_use_case()


def test_connection_test_unknown_provider_500_with_code():
    uc = AsyncMock()
    uc.test_connection.side_effect = UnsupportedVisionProviderError(
        "gemini", ("openai",)
    )
    r = _client(uc).post(f"{BASE}/test")
    assert r.status_code == 500
    assert r.json()["detail"]["code"] == "UNSUPPORTED_VISION_PROVIDER"
