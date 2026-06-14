"""M4-8: Agent Run Observability Router 통합 테스트."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.agent_run_router import (
    get_run_detail_use_case,
    get_usage_by_llm_use_case,
    get_usage_by_node_use_case,
    get_usage_by_user_use_case,
    get_usage_me_use_case,
    router,
)
from src.application.agent_run.exceptions import (
    RunAccessDeniedError,
    RunNotFoundError,
)
from src.application.agent_run.use_cases.get_run_detail_use_case import (
    RunDetailDto,
    StepNode,
    ToolCallNode,
)
from src.domain.agent_run.entities import AgentRun, AgentRunStep, ToolCall
from src.domain.agent_run.interfaces import (
    LlmUsageRow,
    NodeUsageRow,
    UserUsageRow,
)
from src.domain.agent_run.value_objects import (
    CostUsd,
    NodeType,
    RunId,
    RunStatus,
    StepStatus,
    TokenUsage,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.interfaces.dependencies.auth import get_current_user


RUN_ID = "11111111-1111-1111-1111-111111111111"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_admin_user() -> User:
    return User(
        email="admin@test.com",
        password_hash="hashed",
        role=UserRole.ADMIN,
        status=UserStatus.APPROVED,
        id=99,
    )


def _make_regular_user(user_id: int = 1) -> User:
    return User(
        email="user@test.com",
        password_hash="hashed",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=user_id,
    )


def _make_app(
    overrides: dict,
    fake_user_func=None,
) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    if fake_user_func is None:
        fake_user_func = _make_admin_user
    app.dependency_overrides[get_current_user] = fake_user_func
    for dep, override in overrides.items():
        app.dependency_overrides[dep] = override
    return TestClient(app)


def _make_run_dto(user_id: str = "1") -> RunDetailDto:
    run = AgentRun(
        id=RunId(RUN_ID),
        conversation_id="conv-1",
        user_id=user_id,
        agent_id="agent-1",
        llm_model_id="m-1",
        user_message_id=1,
        status=RunStatus.SUCCESS,
        langgraph_thread_id="thread-1",
        langsmith_trace_id=None,
        langsmith_run_url=None,
        token_usage=TokenUsage(100, 50, 150),
        cost_usd=CostUsd(),
        llm_call_count=1,
        started_at=_now(),
        ended_at=_now(),
        latency_ms=100,
        error_message=None,
        error_stack=None,
    )
    step = AgentRunStep(
        id="step-1",
        run_id=RunId(RUN_ID),
        step_index=1,
        node_name="supervisor",
        node_type=NodeType.SUPERVISOR,
        llm_model_id=None,
        status=StepStatus.SUCCESS,
        input_summary="in",
        output_summary="out",
        started_at=_now(),
        ended_at=_now(),
        latency_ms=50,
        error_text=None,
    )
    return RunDetailDto(
        run=run,
        steps=[StepNode(step=step, llm_calls=[], tool_calls=[])],
        orphan_llm_calls=[],
    )


# ── GET /agents/runs/{run_id} ────────────────────────────────────


class TestGetRunDetail:
    def test_returns_200_for_owner(self):
        dto = _make_run_dto(user_id="1")  # user_id matches regular user id=1
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=dto)
        client = _make_app(
            {get_run_detail_use_case: lambda: uc},
            fake_user_func=lambda: _make_regular_user(user_id=1),
        )

        resp = client.get(f"/api/v1/agents/runs/{RUN_ID}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["run"]["id"] == RUN_ID
        assert len(body["steps"]) == 1

    def test_returns_200_for_admin(self):
        dto = _make_run_dto(user_id="other-user")
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=dto)
        client = _make_app(
            {get_run_detail_use_case: lambda: uc},
            fake_user_func=_make_admin_user,
        )

        resp = client.get(f"/api/v1/agents/runs/{RUN_ID}")

        assert resp.status_code == 200

    def test_returns_404_when_not_found(self):
        uc = MagicMock()
        uc.execute = AsyncMock(side_effect=RunNotFoundError(RUN_ID))
        client = _make_app({get_run_detail_use_case: lambda: uc})

        resp = client.get(f"/api/v1/agents/runs/{RUN_ID}")

        assert resp.status_code == 404
        assert RUN_ID in resp.json()["detail"]

    def test_returns_403_when_other_user_non_admin(self):
        uc = MagicMock()
        uc.execute = AsyncMock(side_effect=RunAccessDeniedError(RUN_ID))
        client = _make_app(
            {get_run_detail_use_case: lambda: uc},
            fake_user_func=lambda: _make_regular_user(user_id=2),
        )

        resp = client.get(f"/api/v1/agents/runs/{RUN_ID}")

        assert resp.status_code == 403


# ── GET /admin/usage/* ───────────────────────────────────────────


class TestAdminUsage:
    def test_admin_usage_users_returns_200_for_admin(self):
        uc = MagicMock()
        uc.execute = AsyncMock(
            return_value=[
                UserUsageRow("u-1", 1000, Decimal("0.010"), 5),
                UserUsageRow("u-2", 500, Decimal("0.005"), 3),
            ]
        )
        client = _make_app({get_usage_by_user_use_case: lambda: uc})

        resp = client.get("/api/v1/admin/usage/users")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["rows"]) == 2
        assert body["rows"][0]["user_id"] == "u-1"
        assert body["rows"][0]["total_tokens"] == 1000

    def test_admin_usage_llm_models_returns_200_for_admin(self):
        uc = MagicMock()
        uc.execute = AsyncMock(
            return_value=[
                LlmUsageRow("m-1", "openai", "gpt-4o", 12000, Decimal("0.180"), 50)
            ]
        )
        client = _make_app({get_usage_by_llm_use_case: lambda: uc})

        resp = client.get("/api/v1/admin/usage/llm-models")

        assert resp.status_code == 200
        body = resp.json()
        assert body["rows"][0]["model_name"] == "gpt-4o"

    def test_admin_usage_by_node_returns_200_for_admin(self):
        """★ M3 효과."""
        uc = MagicMock()
        uc.execute = AsyncMock(
            return_value=[
                NodeUsageRow("supervisor", 10, 5000, Decimal("0.050")),
                NodeUsageRow("final_answer", 8, 15000, Decimal("0.450")),
            ]
        )
        client = _make_app({get_usage_by_node_use_case: lambda: uc})

        resp = client.get("/api/v1/admin/usage/by-node")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["rows"]) == 2
        assert body["rows"][0]["node_name"] == "supervisor"
        assert body["rows"][1]["total_cost_usd"] == "0.450"

    def test_admin_endpoints_require_admin_role(self):
        """비-admin이 /admin/* 호출 → 403."""
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=[])
        client = _make_app(
            {get_usage_by_node_use_case: lambda: uc},
            fake_user_func=lambda: _make_regular_user(user_id=1),
        )

        resp = client.get("/api/v1/admin/usage/by-node")

        assert resp.status_code == 403

    def test_period_invalid_returns_422(self):
        uc = MagicMock()
        uc.execute = AsyncMock(return_value=[])
        client = _make_app({get_usage_by_user_use_case: lambda: uc})

        # from > to
        resp = client.get(
            "/api/v1/admin/usage/users",
            params={"from": "2026-06-01T00:00:00Z", "to": "2026-05-01T00:00:00Z"},
        )

        assert resp.status_code == 422


# ── GET /usage/me ────────────────────────────────────────────────


class TestUsageMe:
    def test_returns_current_user_usage(self):
        uc = MagicMock()
        uc.execute = AsyncMock(
            return_value=[
                LlmUsageRow("m-1", "openai", "gpt-4o", 100, Decimal("0.01"), 1)
            ]
        )
        client = _make_app(
            {get_usage_me_use_case: lambda: uc},
            fake_user_func=lambda: _make_regular_user(user_id=42),
        )

        resp = client.get("/api/v1/usage/me")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["rows"]) == 1
        # use case 호출 시 user_id가 "42"로 전달됐는지 검증
        call_args = uc.execute.call_args
        assert call_args.args[0] == "42"
