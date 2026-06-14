"""M5 dashboard: 4 신규 라우트 통합 테스트.

- GET /api/v1/admin/usage/summary
- GET /api/v1/admin/usage/timeseries
- GET /api/v1/usage/me/runs        (보안 케이스 포함)
- GET /api/v1/usage/me/timeseries  (보안 케이스 포함)
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.agent_run_router import (
    get_list_my_runs_use_case,
    get_my_usage_timeseries_use_case,
    get_usage_summary_use_case,
    get_usage_timeseries_use_case,
    router,
)
from src.application.agent_run.use_cases.list_runs_use_case import RunListDto
from src.domain.agent_run.entities import AgentRun
from src.domain.agent_run.interfaces import UsageSummaryRow, UsageTimeseriesPoint
from src.domain.agent_run.value_objects import (
    CostUsd,
    RunId,
    RunStatus,
    TokenUsage,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.interfaces.dependencies.auth import get_current_user


RUN_ID_1 = "11111111-1111-1111-1111-111111111111"
FROM = datetime(2026, 5, 1, tzinfo=timezone.utc)
TO = datetime(2026, 5, 31, tzinfo=timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _admin() -> User:
    return User(
        email="admin@test.com",
        password_hash="x",
        role=UserRole.ADMIN,
        status=UserStatus.APPROVED,
        id=99,
    )


def _user() -> User:
    return User(
        email="user@test.com",
        password_hash="x",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=42,
    )


def _make_app(overrides: dict, fake_user_func=None) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = fake_user_func or _admin
    for dep, override in overrides.items():
        app.dependency_overrides[dep] = override
    return TestClient(app)


def _run() -> AgentRun:
    return AgentRun(
        id=RunId(RUN_ID_1),
        conversation_id="conv-1",
        user_id="42",
        agent_id="agent-1",
        llm_model_id="m-1",
        user_message_id=1,
        status=RunStatus.SUCCESS,
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


# ───── /admin/usage/summary ─────────────────────────────────────────


class TestAdminUsageSummary:
    def test_returns_200_with_success_rate(self):
        row = UsageSummaryRow(
            from_dt=FROM, to_dt=TO,
            total_runs=10, success_runs=9, failed_runs=1,
            total_tokens=1234, total_cost_usd=Decimal("0.012345"),
        )
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=row)
        client = _make_app({get_usage_summary_use_case: lambda: uc})

        resp = client.get("/api/v1/admin/usage/summary")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total_runs"] == 10
        assert body["success_runs"] == 9
        assert body["failed_runs"] == 1
        assert body["success_rate"] == 0.9
        assert body["total_tokens"] == 1234
        # admin 컨텍스트 — user_id=None
        uc.execute.assert_awaited_once()
        kwargs = uc.execute.call_args.kwargs
        assert kwargs.get("user_id") is None

    def test_handles_zero_runs_without_division_error(self):
        row = UsageSummaryRow(
            from_dt=FROM, to_dt=TO,
            total_runs=0, success_runs=0, failed_runs=0,
            total_tokens=0, total_cost_usd=Decimal("0"),
        )
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=row)
        client = _make_app({get_usage_summary_use_case: lambda: uc})

        resp = client.get("/api/v1/admin/usage/summary")

        assert resp.status_code == 200
        assert resp.json()["success_rate"] == 0.0

    def test_requires_admin(self):
        uc = MagicMock()
        client = _make_app(
            {get_usage_summary_use_case: lambda: uc},
            fake_user_func=_user,
        )

        resp = client.get("/api/v1/admin/usage/summary")

        assert resp.status_code == 403


# ───── /admin/usage/timeseries ──────────────────────────────────────


class TestAdminUsageTimeseries:
    def test_returns_200_with_bucket_day_points(self):
        points = [
            UsageTimeseriesPoint(
                bucket=date(2026, 5, 1), run_count=3,
                total_tokens=100, total_cost_usd=Decimal("0.001"),
            ),
            UsageTimeseriesPoint(
                bucket=date(2026, 5, 2), run_count=5,
                total_tokens=300, total_cost_usd=Decimal("0.003"),
            ),
        ]
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=points)
        client = _make_app({get_usage_timeseries_use_case: lambda: uc})

        resp = client.get("/api/v1/admin/usage/timeseries")

        assert resp.status_code == 200
        body = resp.json()
        assert body["bucket"] == "day"
        assert len(body["points"]) == 2
        assert body["points"][0]["bucket"] == "2026-05-01"
        assert body["points"][0]["run_count"] == 3
        # admin 컨텍스트 — user_id=None
        kwargs = uc.execute.call_args.kwargs
        assert kwargs.get("user_id") is None

    def test_requires_admin(self):
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=[])
        client = _make_app(
            {get_usage_timeseries_use_case: lambda: uc},
            fake_user_func=_user,
        )

        resp = client.get("/api/v1/admin/usage/timeseries")

        assert resp.status_code == 403


# ───── /usage/me/runs ───────────────────────────────────────────────


class TestUsageMeRuns:
    def test_returns_200_with_force_user_id_from_current_user(self):
        dto = RunListDto(
            rows=[_run()],
            total=1,
            from_dt=None,
            to_dt=None,
            limit=20,
            offset=0,
        )
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=dto)
        client = _make_app(
            {get_list_my_runs_use_case: lambda: uc},
            fake_user_func=_user,
        )

        resp = client.get("/api/v1/usage/me/runs")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        # ★ 보안: user_id 는 current_user.id ("42") 가 강제 주입
        kwargs = uc.execute.call_args.kwargs
        assert kwargs["user_id"] == "42"

    def test_ignores_user_id_query_param(self):
        """★ 보안 케이스: 쿼리 파라미터로 user_id 시도해도 무시됨."""
        dto = RunListDto(
            rows=[],
            total=0,
            from_dt=None,
            to_dt=None,
            limit=20,
            offset=0,
        )
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=dto)
        client = _make_app(
            {get_list_my_runs_use_case: lambda: uc},
            fake_user_func=_user,
        )

        # 공격자가 다른 user_id 시도
        resp = client.get(
            "/api/v1/usage/me/runs",
            params={"user_id": "99-other-user"},
        )

        assert resp.status_code == 200  # FastAPI는 미정의 쿼리를 무시
        # use case 는 항상 current_user.id ("42") 만 사용
        kwargs = uc.execute.call_args.kwargs
        assert kwargs["user_id"] == "42"

    def test_filters_by_agent_id_and_status(self):
        dto = RunListDto(
            rows=[], total=0, from_dt=None, to_dt=None, limit=20, offset=0,
        )
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=dto)
        client = _make_app(
            {get_list_my_runs_use_case: lambda: uc},
            fake_user_func=_user,
        )

        resp = client.get(
            "/api/v1/usage/me/runs",
            params={"agent_id": "a-1", "status": "FAILED"},
        )

        assert resp.status_code == 200
        filters = uc.execute.call_args.kwargs["filters"]
        assert filters.agent_id == "a-1"
        assert filters.status == "FAILED"


# ───── /usage/me/timeseries ─────────────────────────────────────────


class TestUsageMeTimeseries:
    def test_returns_200_with_force_user_id(self):
        points = [
            UsageTimeseriesPoint(
                bucket=date(2026, 5, 1), run_count=1,
                total_tokens=50, total_cost_usd=Decimal("0.0005"),
            ),
        ]
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=points)
        client = _make_app(
            {get_my_usage_timeseries_use_case: lambda: uc},
            fake_user_func=_user,
        )

        resp = client.get("/api/v1/usage/me/timeseries")

        assert resp.status_code == 200
        body = resp.json()
        assert body["bucket"] == "day"
        # ★ 보안: 첫 인자는 current_user.id ("42")
        args = uc.execute.call_args.args
        assert args[0] == "42"

    def test_ignores_user_id_query_param(self):
        """★ 보안 케이스: 쿼리 user_id 시도해도 current_user.id 만 사용."""
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=[])
        client = _make_app(
            {get_my_usage_timeseries_use_case: lambda: uc},
            fake_user_func=_user,
        )

        resp = client.get(
            "/api/v1/usage/me/timeseries",
            params={"user_id": "99-other-user"},
        )

        assert resp.status_code == 200
        args = uc.execute.call_args.args
        assert args[0] == "42"  # current_user.id만
