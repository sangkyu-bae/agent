"""API 테스트: EvalRouter (agent-eval-gate Design §3-4)."""
from datetime import datetime
from types import SimpleNamespace
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
    get_negative_drilldown_use_case,
)
from src.application.agent_run.use_cases.get_message_retrievals_use_case import (
    MessageRunRetrievals,
    QueryRetrievalGroup,
)
from src.application.eval.drilldown_use_case import NegativeDrilldownDto
from src.application.eval.use_cases import AgentEvalStat
from src.domain.agent_run.entities import RetrievalSource
from src.domain.agent_run.value_objects import RunId
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


# ── negative-feedback-drilldown Design §8.2 ─────────────────────

DRILLDOWN_URL = "/api/v1/admin/eval/negative/284/drilldown"
OWNER_ID = "owner-7"
SESSION_ID = "session-445d"
RUN_ID = "5a7d6c11-ecc1-4b05-8fea-66b4123e4f1f"


def _source() -> RetrievalSource:
    return RetrievalSource(
        id="src-1", run_id=RunId(RUN_ID), tool_call_id=None,
        collection_name="kb", document_id="d1", chunk_id="c1", score=0.8,
        rank_index=0, content_preview="근거 미리보기", metadata_json=None,
        created_at=NOW, search_query="재작성 쿼리", query_source="rewrite",
        search_mode="hybrid",
    )


def _drilldown_dto(question: str | None = "질문") -> NegativeDrilldownDto:
    # 실제 런 엔티티처럼 소유자·세션 식별자를 가진 입력을 넣어 응답 누출을 검사한다
    run = SimpleNamespace(
        id=RunId(RUN_ID), agent_id="a1", langsmith_run_url="https://ls/1",
        user_id=OWNER_ID, conversation_id=SESSION_ID,
    )
    group = QueryRetrievalGroup(
        search_query="재작성 쿼리", query_source="rewrite",
        search_mode="hybrid", sources=[_source()],
    )
    return NegativeDrilldownDto(
        message_id=284, agent_id="a1", question=question, answer="답변",
        runs=[MessageRunRetrievals(run=run, groups=[group])],
    )


def _all_keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _all_keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _all_keys(v)}
    return set()


@pytest.fixture
def drilldown(app):
    use_case = MagicMock()
    use_case.execute = AsyncMock(return_value=_drilldown_dto())
    app.dependency_overrides[get_negative_drilldown_use_case] = lambda: use_case
    app.dependency_overrides[get_current_user] = lambda: _user("admin")
    return TestClient(app), use_case


class TestNegativeDrilldown:
    def test_질문_답변_런을_반환한다(self, drilldown):
        c, use_case = drilldown

        r = c.get(DRILLDOWN_URL)

        assert r.status_code == 200
        body = r.json()
        assert body["message_id"] == 284
        assert body["agent_id"] == "a1"
        assert body["question"] == "질문"
        assert body["answer"] == "답변"
        run = body["runs"][0]
        assert run["run_id"] == RUN_ID
        assert run["langsmith_run_url"] == "https://ls/1"
        group = run["groups"][0]
        assert group["search_query"] == "재작성 쿼리"
        assert group["sources"][0]["content_preview"] == "근거 미리보기"

    def test_관리자_id로_UseCase를_호출한다(self, drilldown):
        c, use_case = drilldown

        c.get(DRILLDOWN_URL)

        args = use_case.execute.await_args.args
        assert args[0] == 284
        assert args[1] == "7"
        assert args[2]  # request_id

    def test_응답에_사용자_식별자가_없다(self, drilldown):
        c, _ = drilldown

        r = c.get(DRILLDOWN_URL)

        assert _all_keys(r.json()).isdisjoint(
            {"user_id", "session_id", "conversation_id"}
        )
        assert OWNER_ID not in r.text
        assert SESSION_ID not in r.text

    def test_질문_복원_실패도_200(self, drilldown):
        c, use_case = drilldown
        use_case.execute = AsyncMock(return_value=_drilldown_dto(question=None))

        r = c.get(DRILLDOWN_URL)

        assert r.status_code == 200
        assert r.json()["question"] is None

    def test_찾을_수_없으면_404(self, drilldown):
        c, use_case = drilldown
        use_case.execute = AsyncMock(
            side_effect=ValueError("메시지를 찾을 수 없습니다.")
        )

        r = c.get(DRILLDOWN_URL)

        assert r.status_code == 404
        assert r.json()["detail"] == "메시지를 찾을 수 없습니다."

    def test_비관리자는_403(self, app, drilldown):
        c, use_case = drilldown
        app.dependency_overrides[get_current_user] = lambda: _user("user")

        assert c.get(DRILLDOWN_URL).status_code == 403
        use_case.execute.assert_not_awaited()

    def test_미인증은_401(self, app, drilldown):
        c, use_case = drilldown
        del app.dependency_overrides[get_current_user]

        assert c.get(DRILLDOWN_URL).status_code == 401
        use_case.execute.assert_not_awaited()

    def test_정수가_아닌_id는_422(self, drilldown):
        c, _ = drilldown
        r = c.get("/api/v1/admin/eval/negative/abc/drilldown")
        assert r.status_code == 422
