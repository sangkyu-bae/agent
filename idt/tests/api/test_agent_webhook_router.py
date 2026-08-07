"""API 테스트: AgentWebhookRouter (관리 5종 — 상태코드 매핑, JWT 필수)."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.agent_webhook_router import (
    get_disable_webhook_use_case,
    get_enable_webhook_use_case,
    get_get_webhook_use_case,
    get_list_webhook_deliveries_use_case,
    get_rotate_webhook_use_case,
    get_update_webhook_use_case,
    router,
)
from src.application.agent_webhook.errors import WebhookValidationError
from src.application.agent_webhook.schemas import (
    WebhookConfigResponse,
    WebhookDeliveryResponse,
    WebhookSecretResponse,
)
from src.interfaces.dependencies.auth import get_current_user

AGENT_ID = "a1"


def _secret_response() -> WebhookSecretResponse:
    return WebhookSecretResponse(
        secret="whsec_plain_once_1234",
        secret_hint="1234",
        enabled=True,
        inbound_path=f"/api/v1/webhooks/agents/{AGENT_ID}",
        created_at="2026-08-07T00:00:00",
    )


def _config_response(**overrides) -> WebhookConfigResponse:
    base = dict(
        configured=True,
        enabled=True,
        secret_hint="1234",
        inbound_path=f"/api/v1/webhooks/agents/{AGENT_ID}",
        outbound_url=None,
        outbound_enabled=False,
        created_at="2026-08-07T00:00:00",
    )
    base.update(overrides)
    return WebhookConfigResponse(**base)


@pytest.fixture
def mock_ucs():
    ucs = {
        name: MagicMock()
        for name in ["enable", "get", "rotate", "update", "disable", "deliveries"]
    }
    ucs["enable"].execute = AsyncMock(return_value=_secret_response())
    ucs["get"].execute = AsyncMock(return_value=_config_response())
    ucs["rotate"].execute = AsyncMock(return_value=_secret_response())
    ucs["update"].execute = AsyncMock(
        return_value=_config_response(enabled=False)
    )
    ucs["disable"].execute = AsyncMock(return_value=None)
    ucs["deliveries"].execute = AsyncMock(
        return_value=[
            WebhookDeliveryResponse(
                id="d1", trigger_source="schedule", success=True,
                status_code=200, attempts=1, error=None, duration_ms=42,
                created_at="2026-08-07T00:00:00",
            )
        ]
    )
    return ucs


@pytest.fixture
def client(mock_ucs):
    app = FastAPI()
    app.include_router(router)
    user = MagicMock()
    user.id = 10
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_enable_webhook_use_case] = (
        lambda: mock_ucs["enable"]
    )
    app.dependency_overrides[get_get_webhook_use_case] = (
        lambda: mock_ucs["get"]
    )
    app.dependency_overrides[get_rotate_webhook_use_case] = (
        lambda: mock_ucs["rotate"]
    )
    app.dependency_overrides[get_update_webhook_use_case] = (
        lambda: mock_ucs["update"]
    )
    app.dependency_overrides[get_disable_webhook_use_case] = (
        lambda: mock_ucs["disable"]
    )
    app.dependency_overrides[get_list_webhook_deliveries_use_case] = (
        lambda: mock_ucs["deliveries"]
    )
    return TestClient(app)


class TestEnableWebhook:
    def test_create_returns_201_with_plain_secret(self, client):
        res = client.post(f"/api/v1/agents/{AGENT_ID}/webhook")
        assert res.status_code == 201
        assert res.json()["secret"] == "whsec_plain_once_1234"

    def test_conflict_returns_409(self, client, mock_ucs):
        mock_ucs["enable"].execute = AsyncMock(
            side_effect=ValueError("이미 활성화된 웹훅이 있습니다")
        )
        res = client.post(f"/api/v1/agents/{AGENT_ID}/webhook")
        assert res.status_code == 409

    def test_non_owner_returns_403(self, client, mock_ucs):
        mock_ucs["enable"].execute = AsyncMock(
            side_effect=PermissionError("본인 소유")
        )
        res = client.post(f"/api/v1/agents/{AGENT_ID}/webhook")
        assert res.status_code == 403

    def test_missing_agent_returns_404(self, client, mock_ucs):
        mock_ucs["enable"].execute = AsyncMock(
            side_effect=ValueError("에이전트를 찾을 수 없습니다")
        )
        res = client.post(f"/api/v1/agents/{AGENT_ID}/webhook")
        assert res.status_code == 404


class TestGetWebhook:
    def test_returns_config_without_secret(self, client):
        res = client.get(f"/api/v1/agents/{AGENT_ID}/webhook")
        assert res.status_code == 200
        body = res.json()
        assert body["secret_hint"] == "1234"
        assert "secret" not in body

    def test_unconfigured_returns_configured_false(self, client, mock_ucs):
        mock_ucs["get"].execute = AsyncMock(
            return_value=WebhookConfigResponse(configured=False)
        )
        res = client.get(f"/api/v1/agents/{AGENT_ID}/webhook")
        assert res.status_code == 200
        assert res.json()["configured"] is False


class TestRotateWebhook:
    def test_rotate_returns_new_secret(self, client):
        res = client.post(f"/api/v1/agents/{AGENT_ID}/webhook/rotate")
        assert res.status_code == 200
        assert res.json()["secret"].startswith("whsec_")

    def test_unconfigured_returns_404(self, client, mock_ucs):
        mock_ucs["rotate"].execute = AsyncMock(
            side_effect=ValueError("웹훅을 찾을 수 없습니다")
        )
        res = client.post(f"/api/v1/agents/{AGENT_ID}/webhook/rotate")
        assert res.status_code == 404


class TestUpdateWebhook:
    def test_toggle_enabled(self, client):
        res = client.patch(
            f"/api/v1/agents/{AGENT_ID}/webhook", json={"enabled": False}
        )
        assert res.status_code == 200
        assert res.json()["enabled"] is False

    def test_invalid_body_returns_422(self, client):
        """빈 body — M2 all-optional 전환 후에도 스키마 validator가 422 유지."""
        res = client.patch(f"/api/v1/agents/{AGENT_ID}/webhook", json={})
        assert res.status_code == 422

    def test_outbound_validation_error_returns_422(self, client, mock_ucs):
        """M2 D19: 전용 예외 WebhookValidationError → 422."""
        mock_ucs["update"].execute = AsyncMock(
            side_effect=WebhookValidationError("outbound URL을 먼저 등록하세요")
        )
        res = client.patch(
            f"/api/v1/agents/{AGENT_ID}/webhook",
            json={"outbound_enabled": True},
        )
        assert res.status_code == 422
        assert "먼저 등록" in res.json()["detail"]


class TestListDeliveries:
    def test_returns_rows(self, client):
        res = client.get(f"/api/v1/agents/{AGENT_ID}/webhook/deliveries")
        assert res.status_code == 200
        body = res.json()
        assert body[0]["trigger_source"] == "schedule"
        assert "url" not in body[0]

    def test_limit_out_of_range_422(self, client):
        res = client.get(
            f"/api/v1/agents/{AGENT_ID}/webhook/deliveries?limit=101"
        )
        assert res.status_code == 422

    def test_non_owner_403(self, client, mock_ucs):
        mock_ucs["deliveries"].execute = AsyncMock(
            side_effect=PermissionError("본인 소유")
        )
        res = client.get(f"/api/v1/agents/{AGENT_ID}/webhook/deliveries")
        assert res.status_code == 403


class TestDisableWebhook:
    def test_delete_returns_204(self, client):
        res = client.delete(f"/api/v1/agents/{AGENT_ID}/webhook")
        assert res.status_code == 204

    def test_unconfigured_returns_404(self, client, mock_ucs):
        mock_ucs["disable"].execute = AsyncMock(
            side_effect=ValueError("웹훅을 찾을 수 없습니다")
        )
        res = client.delete(f"/api/v1/agents/{AGENT_ID}/webhook")
        assert res.status_code == 404


class TestAuthRequired:
    def test_endpoints_require_jwt(self, mock_ucs):
        """인증 오버라이드 없는 앱에서는 401/403 계열이어야 한다."""
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_enable_webhook_use_case] = (
            lambda: mock_ucs["enable"]
        )
        client = TestClient(app)
        res = client.post(f"/api/v1/agents/{AGENT_ID}/webhook")
        assert res.status_code in (401, 403)
