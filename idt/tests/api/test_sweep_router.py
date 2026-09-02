"""L1 API 테스트: 모델 스윕 엔드포인트 (Design §8.2).

라이브 서버 없이 TestClient로 라우팅·인증·검증·상태코드·응답 형태를 검증한다
(test_ragas_auth_scope.py 선례). UseCase는 mock — DB/LLM에 의존하지 않는다.

Design §4.2는 검증 실패를 400으로 적었으나 구현은 라우터 선례(_raise_eval_error)를
따라 **422**를 반환한다. 이 테스트가 실제 계약의 진실원이다.
"""
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.ragas_router import (
    get_create_sweep_use_case,
    get_delete_sweep_use_case,
    get_estimate_sweep_use_case,
    get_list_sweeps_use_case,
    get_sweep_detail_use_case,
    router,
)
from src.application.eval_sweep.schemas import (
    CreateSweepResponse,
    PerModelEstimate,
    SweepDetailResponse,
    SweepEstimateResponse,
    SweepRowResponse,
    SweepSummaryResponse,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.interfaces.dependencies.auth import get_current_user

NOW = datetime(2026, 9, 2)


def _user(role="user", user_id=7) -> User:
    return User(
        email="u@example.com", password_hash="h",
        role=UserRole(role), status=UserStatus.APPROVED, id=user_id,
    )


def _summary(**over) -> SweepSummaryResponse:
    base = dict(
        id="sw-1", name="여신심사봇 모델 비교", agent_id="ag-1", testset_id="ts-1",
        judge_llm_model_id="m-judge", temperature=0.0, status="completed",
        total_runs=2, completed_runs=2, estimated_cost_usd=Decimal("1.842000"),
        created_at=NOW, completed_at=NOW,
    )
    base.update(over)
    return SweepSummaryResponse(**base)


def _detail() -> SweepDetailResponse:
    return SweepDetailResponse(
        **_summary().model_dump(),
        model_ids=["m-1", "m-2"],
        metrics=["answer_relevancy"],
        agent_name="여신심사봇",
        testset_name="여신 골든셋 v3",
        case_count=20,
        actual_cost_usd=Decimal("1.611200"),
        rows=[
            SweepRowResponse(
                run_id="r-1", llm_model_id="m-1", llm_model_name="GPT-4o",
                status="completed", quality={"answer_relevancy": 0.91},
                cost_usd=Decimal("1.104000"), latency_p50_ms=4210,
                latency_p95_ms=8740, tool_f1=0.92,
                measured_cases=20, failed_cases=0,
            ),
            SweepRowResponse(
                run_id="r-2", llm_model_id="m-2", llm_model_name="Qwen (NPU)",
                status="failed", quality={}, cost_usd=None,
                latency_p50_ms=None, latency_p95_ms=None, tool_f1=None,
                measured_cases=0, failed_cases=20,
                error_message="connection refused",
            ),
        ],
    )


def _estimate() -> SweepEstimateResponse:
    return SweepEstimateResponse(
        case_count=20, model_count=2, total_calls=40,
        estimated_cost_usd=Decimal("1.842000"), estimated_minutes=14,
        basis={"source": "ai_run_recent_avg", "sample_size": 37},
        per_model=[
            PerModelEstimate(
                llm_model_id="m-1", display_name="GPT-4o",
                estimated_cost_usd=Decimal("1.104000"),
            )
        ],
    )


CREATE_BODY = {
    "name": "여신심사봇 모델 비교",
    "agent_id": "ag-1",
    "testset_id": "ts-1",
    "model_ids": ["m-1", "m-2"],
    "judge_llm_model_id": "m-judge",
    "metrics": ["answer_relevancy"],
}
ESTIMATE_BODY = {k: v for k, v in CREATE_BODY.items() if k != "name"}


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    return a


@pytest.fixture
def mocks(app):
    create_uc = MagicMock()
    create_uc.execute = AsyncMock(
        return_value=CreateSweepResponse(
            sweep_id="sw-1", status="pending", total_runs=2,
            estimated_cost_usd=Decimal("1.842000"), message="시작됨",
        )
    )
    estimate_uc = MagicMock()
    estimate_uc.execute = AsyncMock(return_value=_estimate())
    detail_uc = MagicMock()
    detail_uc.execute = AsyncMock(return_value=_detail())
    list_uc = MagicMock()
    list_uc.execute = AsyncMock(return_value=([_summary()], 1))
    delete_uc = MagicMock()
    delete_uc.execute = AsyncMock(return_value=None)

    app.dependency_overrides[get_create_sweep_use_case] = lambda: create_uc
    app.dependency_overrides[get_estimate_sweep_use_case] = lambda: estimate_uc
    app.dependency_overrides[get_sweep_detail_use_case] = lambda: detail_uc
    app.dependency_overrides[get_list_sweeps_use_case] = lambda: list_uc
    app.dependency_overrides[get_delete_sweep_use_case] = lambda: delete_uc
    return {
        "create": create_uc, "estimate": estimate_uc,
        "detail": detail_uc, "list": list_uc, "delete": delete_uc,
    }


def _client(app, user=None) -> TestClient:
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


# ── L1-1 / L1-11: 인증 ────────────────────────────────────────────────


class TestAuth:
    def test_l1_11_unauthenticated_is_rejected(self, app, mocks):
        """토큰 없이 접근하면 UseCase까지 도달하지 못한다."""
        res = TestClient(app).get("/api/ragas/sweeps")

        assert res.status_code in (401, 403)
        mocks["list"].execute.assert_not_awaited()


# ── L1-1: 비용 추정 ───────────────────────────────────────────────────


class TestEstimate:
    def test_l1_1_returns_estimate_with_per_model_breakdown(self, app, mocks):
        res = _client(app, _user()).post(
            "/api/ragas/sweeps/estimate", json=ESTIMATE_BODY
        )

        assert res.status_code == 200
        body = res.json()
        assert Decimal(body["estimated_cost_usd"]) > 0
        assert len(body["per_model"]) == 1
        assert body["basis"]["source"] == "ai_run_recent_avg"

    def test_estimate_has_no_side_effect(self, app, mocks):
        """추정은 조회다 — 스윕을 만들면 안 된다."""
        _client(app, _user()).post("/api/ragas/sweeps/estimate", json=ESTIMATE_BODY)

        mocks["create"].execute.assert_not_awaited()


# ── L1-2 ~ L1-5: 스윕 생성 ────────────────────────────────────────────


class TestCreate:
    def test_l1_4_accepted_with_202(self, app, mocks):
        res = _client(app, _user()).post("/api/ragas/sweeps", json=CREATE_BODY)

        assert res.status_code == 202
        assert res.json()["total_runs"] == 2

    def test_owner_is_passed_from_token(self, app, mocks):
        _client(app, _user(user_id=7)).post("/api/ragas/sweeps", json=CREATE_BODY)

        assert mocks["create"].execute.await_args.kwargs["user_id"] == "7"

    def test_l1_2_too_many_models_is_rejected(self, app, mocks):
        mocks["create"].execute = AsyncMock(
            side_effect=ValueError("스윕당 모델은 최대 5개입니다 (선택: 6개)")
        )

        res = _client(app, _user()).post(
            "/api/ragas/sweeps",
            json={**CREATE_BODY, "model_ids": [f"m-{i}" for i in range(6)]},
        )

        # Design §4.2는 400이라 적었으나 라우터 선례상 422다
        assert res.status_code == 422
        assert "최대 5개" in res.json()["detail"]

    def test_l1_3_inactive_model_is_rejected(self, app, mocks):
        mocks["create"].execute = AsyncMock(
            side_effect=ValueError("비활성 모델은 사용할 수 없습니다: GPT-4o")
        )

        res = _client(app, _user()).post("/api/ragas/sweeps", json=CREATE_BODY)

        assert res.status_code == 422
        assert "비활성" in res.json()["detail"]

    def test_l1_5_unowned_testset_is_hidden_as_404(self, app, mocks):
        """403이면 '그 id는 존재한다'는 정보가 샌다 (§7)."""
        mocks["create"].execute = AsyncMock(
            side_effect=ValueError("테스트셋을 찾을 수 없습니다")
        )

        res = _client(app, _user()).post("/api/ragas/sweeps", json=CREATE_BODY)

        assert res.status_code == 404

    def test_missing_required_field_is_422(self, app, mocks):
        res = _client(app, _user()).post(
            "/api/ragas/sweeps", json={"agent_id": "ag-1"}
        )

        assert res.status_code == 422


# ── L1-6 / L1-7: 상세 조회 ────────────────────────────────────────────


class TestDetail:
    def test_l1_6_returns_row_per_model_with_four_axes(self, app, mocks):
        res = _client(app, _user()).get("/api/ragas/sweeps/sw-1")

        assert res.status_code == 200
        body = res.json()
        assert len(body["rows"]) == 2
        row = body["rows"][0]
        for key in ("quality", "cost_usd", "latency_p50_ms", "tool_f1"):
            assert key in row

    def test_detail_exposes_experiment_conditions_and_actual_cost(self, app, mocks):
        """Act에서 보강한 G-1·G-2 필드가 실제 응답에 실린다."""
        body = _client(app, _user()).get("/api/ragas/sweeps/sw-1").json()

        assert body["agent_name"] == "여신심사봇"
        assert body["testset_name"] == "여신 골든셋 v3"
        assert body["case_count"] == 20
        assert Decimal(body["actual_cost_usd"]) == Decimal("1.611200")

    def test_unmeasured_metrics_serialize_as_null_not_zero(self, app, mocks):
        """§3.5 — N/A는 null이어야 프론트가 '—'로 렌더한다."""
        failed = _client(app, _user()).get("/api/ragas/sweeps/sw-1").json()["rows"][1]

        assert failed["cost_usd"] is None
        assert failed["latency_p50_ms"] is None
        assert failed["tool_f1"] is None
        assert failed["status"] == "failed"

    def test_l1_7_other_users_sweep_is_404(self, app, mocks):
        mocks["detail"].execute = AsyncMock(
            side_effect=ValueError("스윕을 찾을 수 없습니다")
        )

        res = _client(app, _user()).get("/api/ragas/sweeps/sw-1")

        assert res.status_code == 404

    def test_admin_scope_is_none(self, app, mocks):
        _client(app, _user(role="admin", user_id=1)).get("/api/ragas/sweeps/sw-1")

        assert mocks["detail"].execute.await_args.kwargs["scope_user_id"] is None

    def test_normal_user_scope_is_own_id(self, app, mocks):
        _client(app, _user(user_id=7)).get("/api/ragas/sweeps/sw-1")

        assert mocks["detail"].execute.await_args.kwargs["scope_user_id"] == "7"


# ── 목록 ──────────────────────────────────────────────────────────────


class TestList:
    def test_returns_paginated_shape(self, app, mocks):
        res = _client(app, _user()).get("/api/ragas/sweeps?limit=20&offset=0")

        assert res.status_code == 200
        body = res.json()
        assert set(body) >= {"items", "total", "limit", "offset"}
        assert body["total"] == 1

    def test_limit_out_of_range_is_422(self, app, mocks):
        res = _client(app, _user()).get("/api/ragas/sweeps?limit=999")

        assert res.status_code == 422


# ── L1-8: 삭제 ────────────────────────────────────────────────────────


class TestDelete:
    def test_l1_8_returns_204(self, app, mocks):
        res = _client(app, _user()).delete("/api/ragas/sweeps/sw-1")

        assert res.status_code == 204

    def test_delete_of_other_users_sweep_is_404(self, app, mocks):
        mocks["delete"].execute = AsyncMock(
            side_effect=ValueError("스윕을 찾을 수 없습니다")
        )

        res = _client(app, _user()).delete("/api/ragas/sweeps/sw-1")

        assert res.status_code == 404
