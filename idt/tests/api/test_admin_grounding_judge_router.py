"""admin_grounding_judge_router L1 — Design §4.2 (answer-citation-verification)."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from src.api.routes.admin_grounding_judge_router import (
    get_grounding_judge_setting_use_case,
    router,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.grounding_judge_setting.exceptions import (
    JudgeModelKindInvalidError,
    JudgeModelNotFoundError,
)
from src.domain.grounding_judge_setting.models import (
    EffectiveJudgeModel,
    GroundingJudgeSetting,
)
from src.interfaces.dependencies.auth import get_current_user

URL = "/api/v1/admin/grounding-judge/settings"
_EFFECTIVE = EffectiveJudgeModel("m-1", "gpt-4o", "GPT-4o", "admin")


def _user(role=UserRole.ADMIN) -> User:
    return User(
        email="a@test.com",
        password_hash="h",
        role=role,
        status=UserStatus.APPROVED,
        id=7,
    )


def _client(uc, user: User | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_grounding_judge_setting_use_case] = lambda: uc
    if user is None:

        def _unauth():
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no token")

        app.dependency_overrides[get_current_user] = _unauth
    else:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def test_get_returns_setting_and_effective_model():
    uc = AsyncMock()
    uc.get.return_value = (GroundingJudgeSetting("m-1"), _EFFECTIVE)
    r = _client(uc, _user()).get(URL)
    assert r.status_code == 200
    assert r.json() == {
        "judge_llm_model_id": "m-1",
        "effective": {
            "model_id": "m-1",
            "model_name": "gpt-4o",
            "display_name": "GPT-4o",
            "source": "admin",
        },
    }


def test_get_effective_may_be_null():
    uc = AsyncMock()
    uc.get.return_value = (GroundingJudgeSetting(), None)
    body = _client(uc, _user()).get(URL).json()
    assert body == {"judge_llm_model_id": None, "effective": None}


def test_put_passes_actor_and_model():
    uc = AsyncMock()
    uc.update.return_value = (GroundingJudgeSetting("m-1"), _EFFECTIVE)
    r = _client(uc, _user()).put(URL, json={"judge_llm_model_id": "m-1"})
    assert r.status_code == 200
    args = uc.update.await_args
    assert args.args[0] == "m-1"
    assert args.kwargs["actor_id"] == "7"


def test_put_null_clears():
    uc = AsyncMock()
    uc.update.return_value = (GroundingJudgeSetting(), None)
    r = _client(uc, _user()).put(URL, json={"judge_llm_model_id": None})
    assert r.status_code == 200
    assert uc.update.await_args.args[0] is None


def test_put_error_codes():
    cases = [
        (JudgeModelNotFoundError("m-1"), "JUDGE_MODEL_NOT_FOUND"),
        (JudgeModelKindInvalidError("m-1"), "JUDGE_MODEL_KIND_INVALID"),
    ]
    for exc, code in cases:
        uc = AsyncMock()
        uc.update.side_effect = exc
        r = _client(uc, _user()).put(URL, json={"judge_llm_model_id": "m-1"})
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == code


def test_non_admin_forbidden_and_anonymous_unauthorized():
    uc = AsyncMock()
    regular = _client(uc, _user(UserRole.USER))
    assert regular.get(URL).status_code == 403
    assert regular.put(URL, json={"judge_llm_model_id": None}).status_code == 403
    assert _client(uc, None).get(URL).status_code == 401
