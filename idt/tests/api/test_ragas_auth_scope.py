"""API 테스트: ragas_router 인증·소유권 스코프 (eval-hub Design §2.2).

- 무토큰 401
- 일반 사용자: scope_user_id=본인 → 본인 것만
- admin: scope_user_id=None → 전체
- 타인/미존재 자원 404 은닉
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.ragas_router import (
    router,
    get_batch_eval_use_case,
    get_eval_result_use_case,
    get_testset_use_case,
    get_testset_generate_use_case,
)
from src.application.ragas.schemas import (
    EvalRunDetailResponse,
    TestsetDetailResponse,
    TestsetResponse,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.interfaces.dependencies.auth import get_current_user

NOW = datetime(2026, 8, 3)


def _user(role="user", user_id=7) -> User:
    return User(
        email="u@example.com", password_hash="h",
        role=UserRole(role), status=UserStatus.APPROVED, id=user_id,
    )


def _testset(user_id="7") -> TestsetResponse:
    return TestsetResponse(
        id="ts-1", name="셋", description="", case_count=1,
        created_at=NOW, user_id=user_id,
    )


def _run_detail() -> EvalRunDetailResponse:
    return EvalRunDetailResponse(
        id="run-1", eval_type="batch", target_type="rag", status="completed",
        total_cases=1, created_at=NOW, completed_at=NOW, summary={},
    )


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    return a


@pytest.fixture
def mocks(app):
    testset_uc = MagicMock()
    testset_uc.list_all = AsyncMock(return_value=([_testset()], 1))
    testset_uc.get_detail = AsyncMock(
        return_value=TestsetDetailResponse(
            id="ts-1", name="셋", description="", case_count=1,
            created_at=NOW, user_id="7", cases=[{"question": "q", "ground_truth": "a"}],
        )
    )
    testset_uc.delete = AsyncMock(return_value=True)
    result_uc = MagicMock()
    result_uc.list_runs = AsyncMock(return_value=([_run_detail()], 1))
    result_uc.get_run_detail = AsyncMock(return_value=_run_detail())
    result_uc.delete_run = AsyncMock(return_value=True)
    batch_uc = MagicMock()
    generate_uc = MagicMock()

    app.dependency_overrides[get_testset_use_case] = lambda: testset_uc
    app.dependency_overrides[get_eval_result_use_case] = lambda: result_uc
    app.dependency_overrides[get_batch_eval_use_case] = lambda: batch_uc
    app.dependency_overrides[get_testset_generate_use_case] = lambda: generate_uc
    return testset_uc, result_uc


class TestAuthRequired:
    @pytest.mark.parametrize("method,path", [
        ("get", "/api/ragas/testsets"),
        ("get", "/api/ragas/testsets/ts-1"),
        ("delete", "/api/ragas/testsets/ts-1"),
        ("get", "/api/ragas/runs"),
        ("get", "/api/ragas/runs/run-1"),
        ("get", "/api/ragas/metrics"),
    ])
    def test_무토큰_401(self, app, mocks, method, path):
        c = TestClient(app)
        assert getattr(c, method)(path).status_code == 401


class TestScope:
    def test_일반사용자_목록은_본인_스코프(self, app, mocks):
        testset_uc, result_uc = mocks
        app.dependency_overrides[get_current_user] = lambda: _user("user")
        c = TestClient(app)

        assert c.get("/api/ragas/testsets").status_code == 200
        assert testset_uc.list_all.await_args.kwargs["scope_user_id"] == "7"

        assert c.get("/api/ragas/runs").status_code == 200
        assert result_uc.list_runs.await_args.kwargs["scope_user_id"] == "7"

    def test_admin_목록은_전체_스코프(self, app, mocks):
        testset_uc, result_uc = mocks
        app.dependency_overrides[get_current_user] = lambda: _user("admin")
        c = TestClient(app)

        c.get("/api/ragas/testsets")
        assert testset_uc.list_all.await_args.kwargs["scope_user_id"] is None

        c.get("/api/ragas/runs")
        assert result_uc.list_runs.await_args.kwargs["scope_user_id"] is None

    def test_타인_테스트셋_상세_404_은닉(self, app, mocks):
        testset_uc, _ = mocks
        testset_uc.get_detail = AsyncMock(return_value=None)
        app.dependency_overrides[get_current_user] = lambda: _user("user")
        c = TestClient(app)
        assert c.get("/api/ragas/testsets/ts-other").status_code == 404

    def test_타인_테스트셋_삭제_404_은닉(self, app, mocks):
        testset_uc, _ = mocks
        testset_uc.delete = AsyncMock(return_value=False)
        app.dependency_overrides[get_current_user] = lambda: _user("user")
        c = TestClient(app)
        assert c.delete("/api/ragas/testsets/ts-other").status_code == 404

    def test_타인_run_상세_404_은닉(self, app, mocks):
        _, result_uc = mocks
        result_uc.get_run_detail = AsyncMock(return_value=None)
        app.dependency_overrides[get_current_user] = lambda: _user("user")
        c = TestClient(app)
        assert c.get("/api/ragas/runs/run-other").status_code == 404

    def test_생성은_본인_user_id_저장(self, app, mocks):
        testset_uc, _ = mocks
        testset_uc.create = AsyncMock(return_value=_testset())
        app.dependency_overrides[get_current_user] = lambda: _user("user")
        c = TestClient(app)

        r = c.post("/api/ragas/testsets", json={
            "name": "셋", "description": "", "cases": [{"question": "q"}],
        })
        assert r.status_code == 201
        assert testset_uc.create.await_args.kwargs["user_id"] == "7"
