"""API 테스트: BackgroundJobRouter (등록·조회·확인·스케줄 이력)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.background_job_router import (
    get_count_unseen_use_case,
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
    JobNotFoundError,
)
from src.application.background_job.schemas import (
    EnqueueJobResponse,
    JobResponse,
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


@pytest.fixture
def mock_ucs():
    ucs = {
        name: MagicMock()
        for name in [
            "enqueue", "list", "get", "unseen", "seen", "seen_all", "sch_runs",
        ]
    }
    ucs["enqueue"].execute = AsyncMock(
        return_value=EnqueueJobResponse(
            job_id="j1", status="queued", request_id="req-1"
        )
    )
    ucs["list"].execute = AsyncMock(return_value=[_job_response()])
    ucs["get"].execute = AsyncMock(return_value=_job_response())
    ucs["unseen"].execute = AsyncMock(return_value=UnseenCountResponse(count=2))
    ucs["seen"].execute = AsyncMock(return_value=None)
    ucs["seen_all"].execute = AsyncMock(return_value=SeenAllResponse(updated=3))
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
    def test_list_jobs(self, client, mock_ucs):
        res = client.get("/api/v1/jobs?status=success&limit=10")
        assert res.status_code == 200
        assert res.json()[0]["id"] == "j1"
        args = mock_ucs["list"].execute.call_args[0]
        assert args[0] == "u1" and args[1] == "success" and args[2] == 10

    def test_invalid_status_filter_422(self, client):
        assert client.get("/api/v1/jobs?status=nope").status_code == 422

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
