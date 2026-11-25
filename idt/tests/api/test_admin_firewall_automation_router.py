"""방화벽 자동 점검 API — firewall-agent design §4.4 (admin 전용)."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes import admin_firewall_router as fw_router
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.firewall_admin.errors import AutomationNotConfiguredError
from src.domain.firewall_admin.models import (
    AutomationAlert,
    AutomationRun,
    AutomationSchedule,
    AutomationSnapshot,
    AutomationState,
)
from src.interfaces.dependencies.auth import get_current_user

URL = "/api/v1/admin/firewall/automation"
NOW = datetime(2026, 11, 24, 5, 0, 0)


def _user(role, uid):
    return User(
        email="x@t", password_hash="h", role=role, status=UserStatus.APPROVED, id=uid
    )


STATE = AutomationState(
    configured=True,
    reason=None,
    snapshot=AutomationSnapshot(
        agent_id="a1",
        agent_name="방화벽 보안 에이전트",
        schedules=(
            AutomationSchedule(
                id="s1",
                name="10분 점검",
                enabled=True,
                cron_expr="*/10 * * * *",
                skip_when_busy=True,
                next_run_at=NOW,
                last_run=AutomationRun(
                    status="skipped", skip_reason="approval_pending", started_at=NOW
                ),
            ),
        ),
        alert=AutomationAlert(
            configured=True,
            enabled=False,
            skip_when_busy=True,
            last_result="duplicate",
            last_received_at=NOW,
        ),
    ),
)


def _client(user, service):
    app = FastAPI()
    app.include_router(fw_router.router)
    app.dependency_overrides[fw_router.get_automation_service] = lambda: service
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture
def service():
    svc = MagicMock()
    svc.state = AsyncMock(return_value=STATE)
    svc.update = AsyncMock(return_value=STATE)
    return svc


def test_get_returns_state(service):
    res = _client(_user(UserRole.ADMIN, 17), service).get(URL)
    assert res.status_code == 200
    body = res.json()
    assert body["configured"] is True and body["agent"] == {
        "id": "a1",
        "name": "방화벽 보안 에이전트",
    }
    (sch,) = body["schedules"]
    assert sch["last_run"] == {
        "status": "skipped",
        "skip_reason": "approval_pending",
        "started_at": "2026-11-24T05:00:00Z",
    }
    assert body["alert_receiver"]["last_result"] == "duplicate"


def test_get_not_configured(service):
    service.state = AsyncMock(
        return_value=AutomationState(
            configured=False, reason="AGENT_NOT_SET", snapshot=None
        )
    )
    body = _client(_user(UserRole.ADMIN, 17), service).get(URL).json()
    assert body == {
        "configured": False,
        "reason": "AGENT_NOT_SET",
        "agent": None,
        "schedules": [],
        "alert_receiver": None,
    }


def test_put_passes_fields_and_admin(service):
    res = _client(_user(UserRole.ADMIN, 17), service).put(
        URL, json={"schedule_enabled": False}
    )
    assert res.status_code == 200
    assert service.update.call_args.kwargs == {
        "schedule_enabled": False,
        "alert_enabled": None,
        "admin_user_id": "17",
    }


def test_put_not_configured_is_422_with_code(service):
    service.update = AsyncMock(side_effect=AutomationNotConfiguredError())
    res = _client(_user(UserRole.ADMIN, 17), service).put(
        URL, json={"alert_enabled": True}
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "AUTOMATION_NOT_CONFIGURED"


def test_put_wrong_type_uses_module_error_shape(service):
    res = _client(_user(UserRole.ADMIN, 17), service).put(
        URL, json={"schedule_enabled": "maybe"}
    )
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize("method", ["get", "put"])
def test_non_admin_is_forbidden(service, method):
    client = _client(_user(UserRole.USER, 2), service)
    res = client.request(method.upper(), URL, json={"schedule_enabled": True})
    assert res.status_code == 403


def test_anonymous_is_401(service):
    assert _client(None, service).get(URL).status_code == 401
