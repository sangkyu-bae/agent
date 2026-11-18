"""POST /api/ragas/batch — allow_supplemental 은 관리자만 (module-7).

일반 사용자가 켜면 403. 관리자는 그대로 유스케이스에 넘긴다.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes.ragas_router import get_batch_eval_use_case, router
from src.application.ragas.schemas import BatchEvalResponse
from src.domain.auth.entities import User, UserRole, UserStatus
from src.interfaces.dependencies.auth import get_current_user

_BODY = {
    "target_type": "agent",
    "metrics": ["answer_relevancy"],
    "testcases": [{"question": "q"}],
    "agent_id": "agent-1",
    "allow_supplemental": True,
}


def _user(role: str) -> User:
    return User(
        email="u@example.com",
        password_hash="h",
        role=UserRole(role),
        status=UserStatus.APPROVED,
        id=7,
    )


@pytest.fixture
def client_and_uc():
    app = FastAPI()
    app.include_router(router)
    uc = MagicMock()
    uc.execute = AsyncMock(
        return_value=BatchEvalResponse(
            run_id="run-1", status="pending", total_cases=1, message="ok"
        )
    )
    app.dependency_overrides[get_batch_eval_use_case] = lambda: uc
    return app, uc


def test_non_admin_cannot_enable_supplemental(client_and_uc):
    app, uc = client_and_uc
    app.dependency_overrides[get_current_user] = lambda: _user("user")
    res = TestClient(app).post("/api/ragas/batch", json=_BODY)
    assert res.status_code == 403
    uc.execute.assert_not_awaited()


def test_admin_request_passes_flag(client_and_uc):
    app, uc = client_and_uc
    app.dependency_overrides[get_current_user] = lambda: _user("admin")
    res = TestClient(app).post("/api/ragas/batch", json=_BODY)
    assert res.status_code == 202
    assert uc.execute.await_args.args[0].allow_supplemental is True


def test_default_is_off_for_everyone(client_and_uc):
    app, uc = client_and_uc
    app.dependency_overrides[get_current_user] = lambda: _user("user")
    body = {k: v for k, v in _BODY.items() if k != "allow_supplemental"}
    assert TestClient(app).post("/api/ragas/batch", json=body).status_code == 202
    assert uc.execute.await_args.args[0].allow_supplemental is False
