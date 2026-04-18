"""Conversation History API 엔드포인트 테스트 (CHAT-HIST-001)."""
from datetime import datetime
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.conversation_history_router import (
    get_history_use_case,
    router,
)
from src.domain.conversation.history_schemas import (
    MessageItem,
    MessageListResponse,
    SessionListResponse,
    SessionSummary,
)


def _build_app(mock_uc) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_history_use_case] = lambda: mock_uc
    return app


class TestGetSessions:
    def test_returns_200_with_sessions(self):
        mock_uc = AsyncMock()
        mock_uc.get_sessions.return_value = SessionListResponse(
            user_id="u-1",
            sessions=[
                SessionSummary(
                    session_id="s-a",
                    message_count=4,
                    last_message="안녕",
                    last_message_at=datetime(2026, 4, 17, 10, 30),
                )
            ],
        )
        client = TestClient(_build_app(mock_uc))

        resp = client.get("/api/v1/conversations/sessions?user_id=u-1")

        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == "u-1"
        assert len(body["sessions"]) == 1
        assert body["sessions"][0]["session_id"] == "s-a"

    def test_missing_user_id_returns_422(self):
        mock_uc = AsyncMock()
        client = TestClient(_build_app(mock_uc))

        resp = client.get("/api/v1/conversations/sessions")

        assert resp.status_code == 422


class TestGetMessages:
    def test_returns_200_with_messages(self):
        mock_uc = AsyncMock()
        mock_uc.get_messages.return_value = MessageListResponse(
            user_id="u-1",
            session_id="s-a",
            messages=[
                MessageItem(
                    id=1,
                    role="user",
                    content="질문",
                    turn_index=1,
                    created_at=datetime(2026, 4, 17, 9),
                )
            ],
        )
        client = TestClient(_build_app(mock_uc))

        resp = client.get(
            "/api/v1/conversations/sessions/s-a/messages?user_id=u-1"
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == "s-a"
        assert len(body["messages"]) == 1
        assert body["messages"][0]["role"] == "user"

    def test_missing_user_id_returns_422(self):
        mock_uc = AsyncMock()
        client = TestClient(_build_app(mock_uc))

        resp = client.get("/api/v1/conversations/sessions/s-a/messages")

        assert resp.status_code == 422

    def test_empty_messages_returns_200_with_empty_array(self):
        mock_uc = AsyncMock()
        mock_uc.get_messages.return_value = MessageListResponse(
            user_id="u-1", session_id="unknown", messages=[]
        )
        client = TestClient(_build_app(mock_uc))

        resp = client.get(
            "/api/v1/conversations/sessions/unknown/messages?user_id=u-1"
        )

        assert resp.status_code == 200
        assert resp.json()["messages"] == []


class TestErrorHandling:
    def test_use_case_exception_returns_500(self):
        mock_uc = AsyncMock()
        mock_uc.get_sessions.side_effect = RuntimeError("DB 오류")
        client = TestClient(_build_app(mock_uc), raise_server_exceptions=False)

        resp = client.get("/api/v1/conversations/sessions?user_id=u-1")

        assert resp.status_code == 500
