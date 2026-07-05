"""API 테스트: AgentScheduleRouter (CRUD 7종 + 외부 트리거)."""
from datetime import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.agent_schedule_router import (
    get_create_schedule_use_case,
    get_delete_schedule_use_case,
    get_get_schedule_use_case,
    get_list_schedule_runs_use_case,
    get_list_schedules_use_case,
    get_toggle_schedule_use_case,
    get_trigger_due_schedules_use_case,
    get_update_schedule_use_case,
    router,
    trigger_router,
)
from src.application.agent_schedule.schemas import (
    ScheduleResponse,
    ScheduleRunResponse,
    ScheduleSpecPayload,
    TriggerResponse,
    TriggerStatusResponse,
)
from src.interfaces.dependencies.auth import get_current_user


def _schedule_response(**overrides) -> ScheduleResponse:
    base = dict(
        id="s1",
        agent_id="a1",
        name="아침 요약",
        spec=ScheduleSpecPayload(schedule_type="daily", time_of_day=time(9, 0)),
        instruction="{today} 시황 요약해줘",
        enabled=True,
        timezone="Asia/Seoul",
        next_run_at="2026-07-03T00:00:00",
        last_run_at=None,
        created_at="2026-07-02T05:00:00",
        updated_at="2026-07-02T05:00:00",
    )
    base.update(overrides)
    return ScheduleResponse(**base)


VALID_BODY = {
    "name": "아침 요약",
    "spec": {"schedule_type": "daily", "time_of_day": "09:00"},
    "instruction": "{today} 시황 요약해줘",
    "timezone": "Asia/Seoul",
    "enabled": True,
}


@pytest.fixture
def mock_ucs():
    ucs = {name: MagicMock() for name in
           ["create", "list", "get", "update", "delete", "toggle", "runs", "trigger"]}
    ucs["create"].execute = AsyncMock(return_value=_schedule_response())
    ucs["list"].execute = AsyncMock(return_value=[_schedule_response()])
    ucs["get"].execute = AsyncMock(return_value=_schedule_response())
    ucs["update"].execute = AsyncMock(return_value=_schedule_response(name="수정"))
    ucs["delete"].execute = AsyncMock(return_value=None)
    ucs["toggle"].execute = AsyncMock(return_value=_schedule_response(enabled=False))
    ucs["runs"].execute = AsyncMock(
        return_value=[
            ScheduleRunResponse(
                id="r1", schedule_id="s1", status="success",
                scheduled_for="2026-07-02T00:00:00",
                started_at="2026-07-02T00:00:05",
                finished_at="2026-07-02T00:01:00",
                session_id="sess-1", run_id="run-1", error_message=None,
            )
        ]
    )
    ucs["trigger"].execute = AsyncMock(
        return_value=TriggerResponse(claimed=2, success=2, failed=0, request_id="req")
    )
    ucs["trigger"].status = MagicMock(
        return_value=TriggerStatusResponse(last_triggered_at=None, last_result=None)
    )
    return ucs


@pytest.fixture
def client(mock_ucs):
    app = FastAPI()
    app.include_router(router)
    app.include_router(trigger_router)
    user = MagicMock()
    user.id = "u1"
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_create_schedule_use_case] = lambda: mock_ucs["create"]
    app.dependency_overrides[get_list_schedules_use_case] = lambda: mock_ucs["list"]
    app.dependency_overrides[get_get_schedule_use_case] = lambda: mock_ucs["get"]
    app.dependency_overrides[get_update_schedule_use_case] = lambda: mock_ucs["update"]
    app.dependency_overrides[get_delete_schedule_use_case] = lambda: mock_ucs["delete"]
    app.dependency_overrides[get_toggle_schedule_use_case] = lambda: mock_ucs["toggle"]
    app.dependency_overrides[get_list_schedule_runs_use_case] = lambda: mock_ucs["runs"]
    app.dependency_overrides[get_trigger_due_schedules_use_case] = (
        lambda: mock_ucs["trigger"]
    )
    return TestClient(app)


class TestScheduleCrudEndpoints:
    def test_create_returns_201(self, client):
        res = client.post("/api/v1/agents/a1/schedules", json=VALID_BODY)
        assert res.status_code == 201
        assert res.json()["instruction"] == "{today} 시황 요약해줘"

    def test_create_permission_error_returns_403(self, client, mock_ucs):
        mock_ucs["create"].execute = AsyncMock(
            side_effect=PermissionError("본인 소유 에이전트에만")
        )
        res = client.post("/api/v1/agents/a1/schedules", json=VALID_BODY)
        assert res.status_code == 403

    def test_create_over_limit_returns_400(self, client, mock_ucs):
        mock_ucs["create"].execute = AsyncMock(
            side_effect=ValueError("에이전트당 스케줄은 최대 10개 입니다")
        )
        res = client.post("/api/v1/agents/a1/schedules", json=VALID_BODY)
        assert res.status_code == 400

    def test_list_returns_200(self, client):
        res = client.get("/api/v1/agents/a1/schedules")
        assert res.status_code == 200
        assert len(res.json()) == 1

    def test_get_not_found_returns_404(self, client, mock_ucs):
        mock_ucs["get"].execute = AsyncMock(
            side_effect=ValueError("스케줄을 찾을 수 없습니다: sX")
        )
        res = client.get("/api/v1/agents/a1/schedules/sX")
        assert res.status_code == 404

    def test_update_returns_200(self, client):
        res = client.put("/api/v1/agents/a1/schedules/s1", json=VALID_BODY)
        assert res.status_code == 200
        assert res.json()["name"] == "수정"

    def test_delete_returns_204(self, client):
        res = client.delete("/api/v1/agents/a1/schedules/s1")
        assert res.status_code == 204

    def test_toggle_returns_200(self, client, mock_ucs):
        res = client.patch(
            "/api/v1/agents/a1/schedules/s1/enabled", json={"enabled": False}
        )
        assert res.status_code == 200
        assert res.json()["enabled"] is False
        assert mock_ucs["toggle"].execute.call_args[0][3] is False

    def test_list_runs_returns_200(self, client):
        res = client.get("/api/v1/agents/a1/schedules/s1/runs?limit=10")
        assert res.status_code == 200
        assert res.json()[0]["status"] == "success"


class TestTriggerEndpoint:
    def test_trigger_without_configured_token_returns_503(self, client, monkeypatch):
        monkeypatch.setattr(
            "src.api.routes.agent_schedule_router.settings.scheduler_trigger_token",
            "",
        )
        res = client.post("/api/v1/internal/schedules/trigger")
        assert res.status_code == 503

    def test_trigger_with_wrong_token_returns_401(self, client, monkeypatch):
        monkeypatch.setattr(
            "src.api.routes.agent_schedule_router.settings.scheduler_trigger_token",
            "secret",
        )
        res = client.post(
            "/api/v1/internal/schedules/trigger",
            headers={"X-Scheduler-Token": "wrong"},
        )
        assert res.status_code == 401

    def test_trigger_with_valid_token_returns_result(self, client, monkeypatch):
        monkeypatch.setattr(
            "src.api.routes.agent_schedule_router.settings.scheduler_trigger_token",
            "secret",
        )
        res = client.post(
            "/api/v1/internal/schedules/trigger",
            headers={"X-Scheduler-Token": "secret"},
        )
        assert res.status_code == 200
        assert res.json() == {
            "claimed": 2, "success": 2, "failed": 0, "request_id": "req",
        }

    def test_trigger_status_returns_snapshot(self, client, monkeypatch):
        monkeypatch.setattr(
            "src.api.routes.agent_schedule_router.settings.scheduler_trigger_token",
            "secret",
        )
        res = client.get(
            "/api/v1/internal/schedules/trigger/status",
            headers={"X-Scheduler-Token": "secret"},
        )
        assert res.status_code == 200
        assert res.json()["last_triggered_at"] is None
