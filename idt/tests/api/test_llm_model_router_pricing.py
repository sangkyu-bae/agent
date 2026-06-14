"""M4-9: PATCH /api/v1/llm-models/{id}/pricing 통합 테스트."""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.llm_model_router import (
    get_update_llm_model_pricing_use_case,
    router,
)
from src.application.llm_model.schemas import LlmModelResponse
from src.domain.auth.entities import User, UserRole, UserStatus
from src.interfaces.dependencies.auth import get_current_user


def _make_admin() -> User:
    return User(
        email="admin@test.com",
        password_hash="hashed",
        role=UserRole.ADMIN,
        status=UserStatus.APPROVED,
        id=99,
    )


def _make_regular_user() -> User:
    return User(
        email="user@test.com",
        password_hash="hashed",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=1,
    )


def _make_response(model_id: str = "m-1") -> LlmModelResponse:
    return LlmModelResponse(
        id=model_id,
        provider="openai",
        model_name="gpt-4o",
        display_name="GPT-4o",
        description=None,
        max_tokens=128000,
        is_active=True,
        is_default=False,
        input_price_per_1k_usd=Decimal("0.005"),
        output_price_per_1k_usd=Decimal("0.015"),
        pricing_updated_at=datetime.now(timezone.utc),
    )


def _make_client(overrides: dict, fake_user_func=None) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    if fake_user_func is None:
        fake_user_func = _make_admin
    app.dependency_overrides[get_current_user] = fake_user_func
    for dep, override in overrides.items():
        app.dependency_overrides[dep] = override
    return TestClient(app)


class TestPatchPricing:
    def test_returns_200_with_updated_pricing(self):
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=_make_response("m-target"))
        client = _make_client(
            {get_update_llm_model_pricing_use_case: lambda: uc}
        )

        resp = client.patch(
            "/api/v1/llm-models/m-target/pricing",
            json={
                "input_price_per_1k_usd": "0.005",
                "output_price_per_1k_usd": "0.015",
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "m-target"
        assert body["input_price_per_1k_usd"] == "0.005"
        assert body["output_price_per_1k_usd"] == "0.015"
        # use_case가 호출됨을 검증 → invalidate 의무가 use_case 안에서 호출됨 (M4-7 단위 테스트로 보장)
        uc.execute.assert_awaited_once()

    def test_requires_admin_role(self):
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=_make_response())
        client = _make_client(
            {get_update_llm_model_pricing_use_case: lambda: uc},
            fake_user_func=_make_regular_user,
        )

        resp = client.patch(
            "/api/v1/llm-models/m-1/pricing",
            json={
                "input_price_per_1k_usd": "0.005",
                "output_price_per_1k_usd": "0.015",
            },
        )

        assert resp.status_code == 403
        uc.execute.assert_not_awaited()

    def test_returns_404_when_model_not_found(self):
        uc = MagicMock()
        uc.execute = AsyncMock(side_effect=ValueError("모델을 찾을 수 없습니다: m-ghost"))
        client = _make_client(
            {get_update_llm_model_pricing_use_case: lambda: uc}
        )

        resp = client.patch(
            "/api/v1/llm-models/m-ghost/pricing",
            json={
                "input_price_per_1k_usd": "0.005",
                "output_price_per_1k_usd": "0.015",
            },
        )

        assert resp.status_code == 404
        assert "찾을 수 없" in resp.json()["detail"]

    def test_rejects_negative_prices(self):
        """UpdatePricingRequest validation: ge=0."""
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=_make_response())
        client = _make_client(
            {get_update_llm_model_pricing_use_case: lambda: uc}
        )

        resp = client.patch(
            "/api/v1/llm-models/m-1/pricing",
            json={
                "input_price_per_1k_usd": "-0.001",
                "output_price_per_1k_usd": "0.015",
            },
        )

        assert resp.status_code == 422
