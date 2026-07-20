"""API 테스트: EvalRouter (agent-eval-gate Design §3-4)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.eval_router import (
    router,
    get_submit_feedback_use_case,
    get_get_feedback_use_case,
    get_delete_feedback_use_case,
    get_agent_eval_stats_use_case,
)
from src.application.eval.use_cases import AgentEvalStat
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.eval.entity import MessageFeedback, Rating
from src.interfaces.dependencies.auth import get_current_user

NOW = datetime(2026, 7, 20)


def _user(role="user") -> User:
    return User(
        email="u@example.com", password_hash="h",
        role=UserRole(role), status=UserStatus.APPROVED, id=7,
    )


def _fb(rating=Rating.UP, comment=None):
    return MessageFeedback(
        id=1, message_id=1, user_id="7", agent_id="general-chat",
        rating=rating, comment=comment, created_at=NOW, updated_at=NOW,
    )


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    return a


@pytest.fixture
def client(app):
    submit = MagicMock(); submit.execute = AsyncMock(return_value=_fb())
    get = MagicMock(); get.execute = AsyncMock(return_value=_fb())
    delete = MagicMock(); delete.execute = AsyncMock(return_value=None)
    stats = MagicMock()
    stats.agents = AsyncMock(return_value=[AgentEvalStat("a1", 8, 2, 0.8)])
    stats.recent_negative = AsyncMock(return_value=[_fb(Rating.DOWN, "틀림")])

    app.dependency_overrides[get_submit_feedback_use_case] = lambda: submit
    app.dependency_overrides[get_get_feedback_use_case] = lambda: get
    app.dependency_overrides[get_delete_feedback_use_case] = lambda: delete
    app.dependency_overrides[get_agent_eval_stats_use_case] = lambda: stats
    # require_role은 내부적으로 get_current_user를 쓴다 → admin으로 오버라이드
    app.dependency_overrides[get_current_user] = lambda: _user("admin")
    return TestClient(app), submit, stats


class TestFeedback:
    def test_평가_제출_200(self, client):
        c, submit, _ = client
        r = c.post("/api/v1/conversations/messages/1/feedback", json={"rating": "up"})
        assert r.status_code == 200
        assert r.json()["rating"] == "up"
        assert submit.execute.await_args.args[0] == "7"  # str(user.id)

    def test_취소_시_rating_None(self, app):
        submit = MagicMock(); submit.execute = AsyncMock(return_value=None)
        app.dependency_overrides[get_submit_feedback_use_case] = lambda: submit
        app.dependency_overrides[get_current_user] = lambda: _user()
        c = TestClient(app)

        r = c.post("/api/v1/conversations/messages/1/feedback", json={"rating": "up"})

        assert r.status_code == 200
        assert r.json()["rating"] is None

    def test_미인증_401(self, app):
        # use_case는 오버라이드(placeholder 미발동), 인증은 미오버라이드 → 401
        submit = MagicMock(); submit.execute = AsyncMock(return_value=_fb())
        app.dependency_overrides[get_submit_feedback_use_case] = lambda: submit
        c = TestClient(app)
        assert c.post(
            "/api/v1/conversations/messages/1/feedback", json={"rating": "up"}
        ).status_code == 401

    def test_타_미존재_메시지_404_은닉(self, app):
        submit = MagicMock()
        submit.execute = AsyncMock(side_effect=ValueError("메시지를 찾을 수 없습니다."))
        app.dependency_overrides[get_submit_feedback_use_case] = lambda: submit
        app.dependency_overrides[get_current_user] = lambda: _user()
        c = TestClient(app)

        r = c.post("/api/v1/conversations/messages/9/feedback", json={"rating": "up"})
        assert r.status_code == 404

    def test_불량_rating_422(self, app):
        submit = MagicMock()
        submit.execute = AsyncMock(side_effect=ValueError("지원하지 않는 평가입니다."))
        app.dependency_overrides[get_submit_feedback_use_case] = lambda: submit
        app.dependency_overrides[get_current_user] = lambda: _user()
        c = TestClient(app)

        r = c.post("/api/v1/conversations/messages/1/feedback", json={"rating": "x"})
        assert r.status_code == 422

    def test_조회_없으면_rating_None(self, app):
        get = MagicMock(); get.execute = AsyncMock(return_value=None)
        app.dependency_overrides[get_get_feedback_use_case] = lambda: get
        app.dependency_overrides[get_current_user] = lambda: _user()
        c = TestClient(app)

        r = c.get("/api/v1/conversations/messages/1/feedback")
        assert r.status_code == 200
        assert r.json()["rating"] is None

    def test_삭제_204(self, client):
        c, _, _ = client
        assert c.delete("/api/v1/conversations/messages/1/feedback").status_code == 204


class TestAdminStats:
    def test_에이전트_만족도(self, client):
        c, _, _ = client
        r = c.get("/api/v1/admin/eval/agents")
        assert r.status_code == 200
        assert r.json()[0]["satisfaction"] == 0.8

    def test_최근_부정_피드백(self, client):
        c, _, _ = client
        r = c.get("/api/v1/admin/eval/recent-negative")
        assert r.status_code == 200
        assert r.json()[0]["comment"] == "틀림"
