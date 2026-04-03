"""auto_agent_builder_router 테스트."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.routes.auto_agent_builder_router import (
    router,
    get_auto_build_use_case,
    get_auto_build_reply_use_case,
    get_session_repository,
)
from src.application.auto_agent_builder.schemas import AutoBuildResponse, AutoBuildSessionStatusResponse
from src.domain.auto_agent_builder.schemas import AutoBuildSession
from datetime import datetime, timedelta


def _make_app(build_uc=None, reply_uc=None, session_repo=None) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    if build_uc:
        app.dependency_overrides[get_auto_build_use_case] = lambda: build_uc
    if reply_uc:
        app.dependency_overrides[get_auto_build_reply_use_case] = lambda: reply_uc
    if session_repo:
        app.dependency_overrides[get_session_repository] = lambda: session_repo
    return app


def _make_created_response() -> AutoBuildResponse:
    return AutoBuildResponse(
        status="created",
        session_id="sess-1",
        agent_id="agent-uuid",
        explanation="엑셀 내보내기",
        tool_ids=["excel_export"],
        middlewares_applied=["summarization"],
    )


def _make_clarify_response() -> AutoBuildResponse:
    return AutoBuildResponse(
        status="needs_clarification",
        session_id="sess-1",
        questions=["데이터 소스는?"],
        partial_info="불확실",
    )


class TestAutoBuildEndpoint:

    def test_post_returns_202_on_created(self):
        build_uc = AsyncMock()
        build_uc.execute = AsyncMock(return_value=_make_created_response())
        client = TestClient(_make_app(build_uc=build_uc))

        resp = client.post("/api/v3/agents/auto", json={
            "user_request": "보고서 만들어줘",
            "user_id": "user-1",
            "request_id": "req-1",
        })

        assert resp.status_code == 202
        assert resp.json()["status"] == "created"
        assert resp.json()["agent_id"] == "agent-uuid"

    def test_post_returns_202_on_needs_clarification(self):
        build_uc = AsyncMock()
        build_uc.execute = AsyncMock(return_value=_make_clarify_response())
        client = TestClient(_make_app(build_uc=build_uc))

        resp = client.post("/api/v3/agents/auto", json={
            "user_request": "에이전트 만들어",
            "user_id": "user-1",
            "request_id": "req-2",
        })

        assert resp.status_code == 202
        assert resp.json()["status"] == "needs_clarification"
        assert resp.json()["questions"] == ["데이터 소스는?"]


class TestReplyEndpoint:

    def test_post_reply_returns_created(self):
        reply_uc = AsyncMock()
        reply_uc.execute = AsyncMock(return_value=_make_created_response())
        client = TestClient(_make_app(reply_uc=reply_uc))

        resp = client.post("/api/v3/agents/auto/sess-1/reply", json={
            "answers": ["내부 문서"],
            "request_id": "req-reply-1",
        })

        assert resp.status_code == 200
        assert resp.json()["status"] == "created"

    def test_post_reply_passes_session_id_to_use_case(self):
        reply_uc = AsyncMock()
        reply_uc.execute = AsyncMock(return_value=_make_created_response())
        client = TestClient(_make_app(reply_uc=reply_uc))

        client.post("/api/v3/agents/auto/my-session/reply", json={
            "answers": ["내부 문서"],
            "request_id": "req-3",
        })

        call_args = reply_uc.execute.call_args
        assert call_args[0][0] == "my-session"


class TestSessionStatusEndpoint:

    def test_get_returns_session_status(self):
        now = datetime(2026, 3, 24, 12, 0, 0)
        session = AutoBuildSession(
            session_id="sess-1",
            user_id="user-1",
            user_request="보고서 만들어줘",
            model_name="gpt-4o",
            created_at=now,
            expires_at=now + timedelta(hours=24),
        )
        session.status = "created"
        session.created_agent_id = "agent-uuid"

        session_repo = AsyncMock()
        session_repo.find = AsyncMock(return_value=session)
        client = TestClient(_make_app(session_repo=session_repo))

        resp = client.get("/api/v3/agents/auto/sess-1")

        assert resp.status_code == 200
        assert resp.json()["session_id"] == "sess-1"
        assert resp.json()["status"] == "created"

    def test_get_returns_404_when_session_missing(self):
        session_repo = AsyncMock()
        session_repo.find = AsyncMock(return_value=None)
        client = TestClient(_make_app(session_repo=session_repo))

        resp = client.get("/api/v3/agents/auto/no-such")

        assert resp.status_code == 404
