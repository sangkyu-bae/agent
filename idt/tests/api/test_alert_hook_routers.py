"""API 테스트: 알림 수신 공개 라우터 + 소유자 설정 라우터 — firewall-agent design
§4.1·§6."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes.agent_alert_router import (
    get_get_alert_receiver_use_case,
    get_list_alert_receipts_use_case,
    get_rotate_alert_token_use_case,
    get_upsert_alert_receiver_use_case,
)
from src.api.routes.agent_alert_router import router as manage_router
from src.api.routes.alert_hook_public_router import (
    get_receive_alert_use_case,
)
from src.api.routes.alert_hook_public_router import router as public_router
from src.application.agent_alert.receive_alert_use_case import AlertAuthError
from src.application.agent_alert.schemas import (
    AlertReceiverConfigResponse,
    ReceiveAlertResponse,
    UpsertAlertReceiverResponse,
)
from src.interfaces.dependencies.auth import get_current_user

URL = "/api/v1/alert-hooks/agents/agent-1"


@pytest.fixture
def receive_uc():
    uc = MagicMock()
    uc.execute = AsyncMock(
        return_value=ReceiveAlertResponse(
            result="enqueued", receipt_id="rc-1", job_id="job-1"
        )
    )
    return uc


@pytest.fixture
def public_client(receive_uc, monkeypatch):
    monkeypatch.setattr(
        "src.api.routes.alert_hook_public_router.settings.alert_hook_max_body_bytes",
        1000,
    )
    app = FastAPI()
    app.include_router(public_router)
    app.dependency_overrides[get_receive_alert_use_case] = lambda: receive_uc
    return TestClient(app)


class TestPublicReceive:
    def test_accepted_returns_202_and_passes_raw_body_and_header(
        self, public_client, receive_uc
    ):
        body = b'{"alerts":[],"groupKey":"\xea\xb0\x80"}'
        res = public_client.post(
            URL, content=body, headers={"Authorization": "Bearer t"}
        )
        assert res.status_code == 202
        assert res.json() == {
            "result": "enqueued",
            "receipt_id": "rc-1",
            "job_id": "job-1",
        }
        args = receive_uc.execute.call_args[0]
        assert args[0] == "agent-1" and args[1] == "Bearer t" and args[2] == body

    def test_auth_error_is_401(self, public_client, receive_uc):
        receive_uc.execute = AsyncMock(side_effect=AlertAuthError("unauthorized"))
        res = public_client.post(URL, content=b"{}")
        assert res.status_code == 401
        assert "unauthorized" in res.text

    def test_oversized_body_is_413_without_calling_use_case(
        self, public_client, receive_uc
    ):
        res = public_client.post(
            URL, content=b"x" * 1001, headers={"Authorization": "Bearer t"}
        )
        assert res.status_code == 413
        receive_uc.execute.assert_not_awaited()


# ── 소유자 설정 ─────────────────────────────────────────────────────────


@pytest.fixture
def manage_ucs():
    get_uc, upsert_uc, rotate_uc, list_uc = (MagicMock() for _ in range(4))
    get_uc.execute = AsyncMock(
        return_value=AlertReceiverConfigResponse(configured=False)
    )
    config = AlertReceiverConfigResponse(
        configured=True, enabled=True, token_hint="abcd"
    )
    upsert_uc.execute = AsyncMock(
        return_value=UpsertAlertReceiverResponse(config=config, token="secret-token")
    )
    rotate_uc.execute = AsyncMock(side_effect=LookupError("알림 수신 설정이 없습니다"))
    list_uc.execute = AsyncMock(return_value=[])
    return get_uc, upsert_uc, rotate_uc, list_uc


@pytest.fixture
def manage_client(manage_ucs):
    get_uc, upsert_uc, rotate_uc, list_uc = manage_ucs
    app = FastAPI()
    app.include_router(manage_router)
    app.dependency_overrides[get_current_user] = lambda: MagicMock(id=7)
    app.dependency_overrides[get_get_alert_receiver_use_case] = lambda: get_uc
    app.dependency_overrides[get_upsert_alert_receiver_use_case] = lambda: upsert_uc
    app.dependency_overrides[get_rotate_alert_token_use_case] = lambda: rotate_uc
    app.dependency_overrides[get_list_alert_receipts_use_case] = lambda: list_uc
    return TestClient(app)


class TestManage:
    def test_get_unconfigured(self, manage_client):
        res = manage_client.get("/api/v1/agents/agent-1/alert-receiver")
        assert res.status_code == 200 and res.json()["configured"] is False

    def test_put_returns_token_once(self, manage_client, manage_ucs):
        res = manage_client.put(
            "/api/v1/agents/agent-1/alert-receiver", json={"enabled": True}
        )
        assert res.status_code == 200 and res.json()["token"] == "secret-token"
        args = manage_ucs[1].execute.call_args[0]
        assert args[0] == "agent-1" and args[1] == "7"

    def test_put_rejects_long_prefix(self, manage_client):
        res = manage_client.put(
            "/api/v1/agents/agent-1/alert-receiver",
            json={"instruction_prefix": "x" * 301},
        )
        assert res.status_code == 422

    def test_rotate_without_receiver_is_404(self, manage_client):
        res = manage_client.post("/api/v1/agents/agent-1/alert-receiver/token")
        assert res.status_code == 404

    @pytest.mark.parametrize(
        "exc,code", [(PermissionError("x"), 403), (ValueError("x"), 404)]
    )
    def test_owner_errors_are_mapped(self, manage_client, manage_ucs, exc, code):
        manage_ucs[0].execute = AsyncMock(side_effect=exc)
        res = manage_client.get("/api/v1/agents/agent-1/alert-receiver")
        assert res.status_code == code

    def test_receipts_limit_is_passed(self, manage_client, manage_ucs):
        res = manage_client.get(
            "/api/v1/agents/agent-1/alert-receiver/receipts?limit=5"
        )
        assert res.status_code == 200 and res.json() == []
        assert manage_ucs[3].execute.call_args[0][2] == 5

    def test_requires_login(self, manage_ucs):
        app = FastAPI()
        app.include_router(manage_router)
        app.dependency_overrides[get_get_alert_receiver_use_case] = lambda: manage_ucs[
            0
        ]
        res = TestClient(app).get("/api/v1/agents/agent-1/alert-receiver")
        assert res.status_code == 401
