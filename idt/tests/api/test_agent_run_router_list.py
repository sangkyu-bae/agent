"""M5-6: GET /api/v1/admin/runs 통합 테스트."""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.agent_run_router import (
    get_list_runs_use_case,
    router,
)
from src.application.agent_run.use_cases.list_runs_use_case import RunListDto
from src.domain.agent_run.entities import AgentRun
from src.domain.agent_run.value_objects import (
    CostUsd,
    RunId,
    RunStatus,
    TokenUsage,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.interfaces.dependencies.auth import get_current_user


RUN_ID_1 = "11111111-1111-1111-1111-111111111111"
RUN_ID_2 = "22222222-2222-2222-2222-222222222222"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_admin() -> User:
    return User(
        email="admin@test.com",
        password_hash="x",
        role=UserRole.ADMIN,
        status=UserStatus.APPROVED,
        id=99,
    )


def _make_regular_user() -> User:
    return User(
        email="user@test.com",
        password_hash="x",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=1,
    )


def _make_run(run_id: str, status: RunStatus = RunStatus.SUCCESS) -> AgentRun:
    return AgentRun(
        id=RunId(run_id),
        conversation_id="conv-1",
        user_id="user-1",
        agent_id="agent-1",
        llm_model_id="m-1",
        user_message_id=1,
        status=status,
        langgraph_thread_id="thread-1",
        langsmith_trace_id=None,
        langsmith_run_url=None,
        token_usage=TokenUsage(100, 50, 150),
        cost_usd=CostUsd(total_usd=Decimal("0.0012")),
        llm_call_count=2,
        started_at=_now(),
        ended_at=_now(),
        latency_ms=1200,
        error_message=None,
        error_stack=None,
    )


def _make_app(overrides: dict, fake_user_func=None) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    if fake_user_func is None:
        fake_user_func = _make_admin
    app.dependency_overrides[get_current_user] = fake_user_func
    for dep, override in overrides.items():
        app.dependency_overrides[dep] = override
    return TestClient(app)


class TestAdminRunsList:
    def test_returns_200_with_pagination_meta_for_admin(self):
        runs = [_make_run(RUN_ID_1), _make_run(RUN_ID_2, RunStatus.FAILED)]
        dto = RunListDto(
            rows=runs,
            total=2,
            from_dt=None,
            to_dt=None,
            limit=20,
            offset=0,
        )
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=dto)
        client = _make_app({get_list_runs_use_case: lambda: uc})

        resp = client.get("/api/v1/admin/runs")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert body["limit"] == 20
        assert body["offset"] == 0
        assert len(body["rows"]) == 2
        assert body["rows"][0]["id"] == RUN_ID_1
        assert body["rows"][1]["status"] == "FAILED"

    def test_requires_admin_role(self):
        """★ 회귀 가드: non-admin은 403."""
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=RunListDto([], 0, None, None, 20, 0))
        client = _make_app(
            {get_list_runs_use_case: lambda: uc},
            fake_user_func=_make_regular_user,
        )

        resp = client.get("/api/v1/admin/runs")

        assert resp.status_code == 403
        uc.execute.assert_not_awaited()

    def test_rejects_invalid_status(self):
        uc = MagicMock()
        uc.execute = AsyncMock(side_effect=ValueError("status must be one of [...]"))
        client = _make_app({get_list_runs_use_case: lambda: uc})

        resp = client.get("/api/v1/admin/runs", params={"status": "INVALID"})

        assert resp.status_code == 422
        assert "status" in resp.json()["detail"]

    def test_rejects_limit_over_100(self):
        """FastAPI Query(le=100)이 1차 검증."""
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=RunListDto([], 0, None, None, 20, 0))
        client = _make_app({get_list_runs_use_case: lambda: uc})

        resp = client.get("/api/v1/admin/runs", params={"limit": 200})

        assert resp.status_code == 422

    def test_filters_by_user_id_and_status(self):
        dto = RunListDto(
            rows=[_make_run(RUN_ID_1, RunStatus.FAILED)],
            total=1,
            from_dt=None,
            to_dt=None,
            limit=20,
            offset=0,
        )
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=dto)
        client = _make_app({get_list_runs_use_case: lambda: uc})

        resp = client.get(
            "/api/v1/admin/runs",
            params={"user_id": "user-1", "status": "FAILED"},
        )

        assert resp.status_code == 200
        # use case가 filter와 함께 호출됨
        call_filters = uc.execute.call_args.args[0]
        assert call_filters.user_id == "user-1"
        assert call_filters.status == "FAILED"
