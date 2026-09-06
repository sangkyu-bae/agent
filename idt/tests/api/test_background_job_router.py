"""API 테스트: BackgroundJobRouter (등록·조회·확인·스케줄 이력)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.background_job_router import (
    get_cleanup_jobs_use_case,
    get_count_unseen_use_case,
    get_delete_job_use_case,
    get_list_my_schedules_use_case,
    get_enqueue_job_use_case,
    get_get_job_use_case,
    get_list_jobs_use_case,
    get_list_my_schedule_runs_use_case,
    get_mark_all_seen_use_case,
    get_mark_seen_use_case,
    router,
)
from src.application.background_job.errors import (
    JobConflictError,
    JobDeleteConflictError,
    JobNotFoundError,
)
from src.application.background_job.schemas import (
    CleanupJobsResponse,
    EnqueueJobResponse,
    JobHistoryResponse,
    JobListResponse,
    JobResponse,
    MyScheduleResponse,
    MyScheduleRunResponse,
    SeenAllResponse,
    UnseenCountResponse,
)
from src.interfaces.dependencies.auth import get_auth_context, get_current_user

_NOW = datetime(2026, 8, 11, 3, 0)


def _job_response(job_id="j1", status="success") -> JobResponse:
    return JobResponse(
        id=job_id,
        agent_id="a1",
        source="chat",
        query="시장 조사해줘",
        session_id="sess-1",
        run_id="run-1",
        status=status,
        error_message=None,
        seen_at=None,
        queued_at=_NOW,
        started_at=_NOW,
        finished_at=_NOW,
    )


def _history_item(item_id="j1", item_type="manual") -> JobHistoryResponse:
    return JobHistoryResponse(
        id=item_id,
        type=item_type,
        occurred_at=_NOW,
        title="시장 조사해줘",
        status="failed",
        agent_id="a1",
        agent_name="리서치 봇",
        session_id=None,
        error_message="도구 호출에 실패했습니다",
        seen_at=None,
        started_at=_NOW,
        finished_at=_NOW,
        deletable=item_type == "manual",
    )


@pytest.fixture
def mock_ucs():
    ucs = {
        name: MagicMock()
        for name in [
            "enqueue", "list", "get", "unseen", "seen", "seen_all", "sch_runs",
            "delete", "cleanup", "my_schedules",
        ]
    }
    ucs["enqueue"].execute = AsyncMock(
        return_value=EnqueueJobResponse(
            job_id="j1", status="queued", request_id="req-1"
        )
    )
    ucs["list"].execute = AsyncMock(
        return_value=JobListResponse(items=[_history_item()], total=1)
    )
    ucs["delete"].execute = AsyncMock(return_value=None)
    ucs["cleanup"].execute = AsyncMock(
        return_value=CleanupJobsResponse(deleted=3)
    )
    ucs["get"].execute = AsyncMock(return_value=_job_response())
    ucs["unseen"].execute = AsyncMock(return_value=UnseenCountResponse(count=2))
    ucs["seen"].execute = AsyncMock(return_value=None)
    ucs["seen_all"].execute = AsyncMock(return_value=SeenAllResponse(updated=3))
    ucs["my_schedules"].execute = AsyncMock(
        return_value=[
            MyScheduleResponse(
                id="s1",
                agent_id="a1",
                agent_name="리서치 봇",
                name="아침 요약",
                spec={"schedule_type": "daily", "time_of_day": "09:00"},
                instruction="오늘 뉴스 요약해줘",
                enabled=True,
                timezone="Asia/Seoul",
                next_run_at="2026-09-04T00:00:00",
                last_run_at=None,
            )
        ]
    )
    ucs["sch_runs"].execute = AsyncMock(
        return_value=[
            MyScheduleRunResponse(
                id="r1",
                schedule_id="s1",
                schedule_name="아침 요약",
                agent_id="a1",
                status="success",
                scheduled_for=_NOW,
                started_at=_NOW,
                finished_at=_NOW,
                session_id="sess-1",
                error_message=None,
            )
        ]
    )
    return ucs


@pytest.fixture
def client(mock_ucs):
    app = FastAPI()
    app.include_router(router)
    user = MagicMock()
    user.id = "u1"
    auth_ctx = MagicMock()
    auth_ctx.user_id = "u1"
    auth_ctx.department_ids = ["d1"]
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_auth_context] = lambda: auth_ctx
    app.dependency_overrides[get_enqueue_job_use_case] = lambda: mock_ucs["enqueue"]
    app.dependency_overrides[get_list_jobs_use_case] = lambda: mock_ucs["list"]
    app.dependency_overrides[get_get_job_use_case] = lambda: mock_ucs["get"]
    app.dependency_overrides[get_count_unseen_use_case] = lambda: mock_ucs["unseen"]
    app.dependency_overrides[get_mark_seen_use_case] = lambda: mock_ucs["seen"]
    app.dependency_overrides[get_mark_all_seen_use_case] = (
        lambda: mock_ucs["seen_all"]
    )
    app.dependency_overrides[get_list_my_schedule_runs_use_case] = (
        lambda: mock_ucs["sch_runs"]
    )
    app.dependency_overrides[get_delete_job_use_case] = lambda: mock_ucs["delete"]
    app.dependency_overrides[get_cleanup_jobs_use_case] = (
        lambda: mock_ucs["cleanup"]
    )
    app.dependency_overrides[get_list_my_schedules_use_case] = (
        lambda: mock_ucs["my_schedules"]
    )
    return TestClient(app)


class TestEnqueue:
    def test_returns_202_with_job_id(self, client, mock_ucs):
        res = client.post("/api/v1/agents/a1/jobs", json={"query": "조사해줘"})
        assert res.status_code == 202
        assert res.json()["job_id"] == "j1"
        args = mock_ucs["enqueue"].execute.call_args[0]
        assert args[0] == "a1" and args[2] == "u1" and args[3] == ["d1"]

    def test_session_conflict_maps_409(self, client, mock_ucs):
        mock_ucs["enqueue"].execute = AsyncMock(
            side_effect=JobConflictError("진행 중")
        )
        res = client.post(
            "/api/v1/agents/a1/jobs",
            json={"query": "q", "session_id": "sess-1"},
        )
        assert res.status_code == 409

    def test_not_found_maps_404(self, client, mock_ucs):
        mock_ucs["enqueue"].execute = AsyncMock(
            side_effect=JobNotFoundError("없음")
        )
        res = client.post("/api/v1/agents/nope/jobs", json={"query": "q"})
        assert res.status_code == 404

    def test_empty_query_rejected_422(self, client):
        res = client.post("/api/v1/agents/a1/jobs", json={"query": ""})
        assert res.status_code == 422


class TestQuery:
    def test_list_jobs_returns_items_and_total(self, client, mock_ucs):
        res = client.get("/api/v1/jobs")
        assert res.status_code == 200
        body = res.json()
        assert body["items"][0]["id"] == "j1"
        assert body["total"] == 1
        assert body["items"][0]["deletable"] is True

    def test_filters_forwarded_to_use_case(self, client, mock_ucs):
        res = client.get(
            "/api/v1/jobs?status=done&type=manual&period=today&limit=10&offset=20"
        )
        assert res.status_code == 200
        args = mock_ucs["list"].execute.call_args[0]
        assert args[0] == "u1"
        assert args[1] == "done"
        assert args[2] == "manual"
        assert args[3] == "today"
        assert args[4] == 10 and args[5] == 20

    def test_defaults_are_all(self, client, mock_ucs):
        client.get("/api/v1/jobs")
        args = mock_ucs["list"].execute.call_args[0]
        assert args[1:4] == ("all", "all", "all")

    @pytest.mark.parametrize(
        "qs",
        ["status=success", "type=nope", "period=month", "limit=0", "limit=101"],
    )
    def test_invalid_filters_422(self, client, qs):
        assert client.get(f"/api/v1/jobs?{qs}").status_code == 422

    def test_unseen_count_not_swallowed_by_job_id_route(self, client, mock_ucs):
        """D14: /jobs/unseen-count 가 /jobs/{job_id} 에 매칭되지 않아야 한다."""
        mock_ucs["get"].execute = AsyncMock(side_effect=JobNotFoundError("없음"))
        res = client.get("/api/v1/jobs/unseen-count")
        assert res.status_code == 200
        assert res.json()["count"] == 2

    def test_get_job_not_found_404(self, client, mock_ucs):
        mock_ucs["get"].execute = AsyncMock(side_effect=JobNotFoundError("없음"))
        assert client.get("/api/v1/jobs/other").status_code == 404


class TestSeen:
    def test_mark_seen_204(self, client, mock_ucs):
        res = client.post("/api/v1/jobs/j1/seen")
        assert res.status_code == 204
        assert mock_ucs["seen"].execute.call_args[0][:2] == ("j1", "u1")

    def test_mark_seen_not_owned_404(self, client, mock_ucs):
        mock_ucs["seen"].execute = AsyncMock(side_effect=JobNotFoundError("없음"))
        assert client.post("/api/v1/jobs/j9/seen").status_code == 404

    def test_seen_all_returns_updated(self, client):
        res = client.post("/api/v1/jobs/seen-all")
        assert res.status_code == 200
        assert res.json()["updated"] == 3


class TestDelete:
    def test_delete_returns_204(self, client, mock_ucs):
        res = client.delete("/api/v1/jobs/j1")
        assert res.status_code == 204
        assert mock_ucs["delete"].execute.call_args[0][:2] == ("j1", "u1")

    def test_active_job_delete_maps_409(self, client, mock_ucs):
        mock_ucs["delete"].execute = AsyncMock(
            side_effect=JobDeleteConflictError("진행 중인 작업은 삭제할 수 없습니다")
        )
        assert client.delete("/api/v1/jobs/j1").status_code == 409

    def test_not_owned_delete_maps_404(self, client, mock_ucs):
        mock_ucs["delete"].execute = AsyncMock(side_effect=JobNotFoundError("없음"))
        assert client.delete("/api/v1/jobs/j9").status_code == 404


class TestCleanup:
    def test_cleanup_returns_deleted_count(self, client):
        res = client.post("/api/v1/jobs/cleanup")
        assert res.status_code == 200
        assert res.json()["deleted"] == 3

    def test_cleanup_not_swallowed_by_job_id_route(self, client, mock_ucs):
        """D14: /jobs/cleanup 이 /jobs/{job_id} 에 매칭되면 404 가 난다."""
        mock_ucs["get"].execute = AsyncMock(side_effect=JobNotFoundError("없음"))
        assert client.post("/api/v1/jobs/cleanup").status_code == 200


class TestMySchedules:
    def test_lists_my_schedule_definitions(self, client, mock_ucs):
        res = client.get("/api/v1/schedules")
        assert res.status_code == 200
        body = res.json()
        assert body[0]["name"] == "아침 요약"
        # 관리 경로(/agents/{id}/schedules) 조립에 필요하다
        assert body[0]["agent_id"] == "a1"
        assert body[0]["enabled"] is True
        assert mock_ucs["my_schedules"].execute.call_args[0][0] == "u1"


class TestScheduleRuns:
    def test_lists_my_schedule_runs(self, client, mock_ucs):
        res = client.get("/api/v1/schedule-runs")
        assert res.status_code == 200
        body = res.json()
        assert body[0]["schedule_name"] == "아침 요약"
        assert mock_ucs["sch_runs"].execute.call_args[0][0] == "u1"


class TestAuthRequired:
    def test_endpoints_reject_without_auth(self, mock_ucs):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_list_jobs_use_case] = lambda: mock_ucs["list"]
        client = TestClient(app)
        res = client.get("/api/v1/jobs")
        assert res.status_code in (401, 403)
