"""Conversation API 엔드포인트 단위 테스트."""
import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.conversation_router import router, get_conversation_use_case
from src.domain.conversation.schemas import ConversationChatResponse


def _build_app(mock_uc) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_conversation_use_case] = lambda: mock_uc
    return app


def _ok_response(
    user_id: str = "u-1",
    session_id: str = "s-1",
    answer: str = "답변입니다.",
    was_summarized: bool = False,
    request_id: str = "req-1",
) -> ConversationChatResponse:
    return ConversationChatResponse(
        user_id=user_id,
        session_id=session_id,
        answer=answer,
        was_summarized=was_summarized,
        request_id=request_id,
    )


class TestConversationRouterChat:
    def test_chat_returns_200(self):
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = _ok_response()
        client = TestClient(_build_app(mock_uc))

        resp = client.post(
            "/api/v1/conversation/chat",
            json={"user_id": "u-1", "session_id": "s-1", "message": "안녕하세요"},
        )

        assert resp.status_code == 200

    def test_chat_response_fields(self):
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = _ok_response(
            answer="좋은 날씨네요", was_summarized=True
        )
        client = TestClient(_build_app(mock_uc))

        resp = client.post(
            "/api/v1/conversation/chat",
            json={"user_id": "u-1", "session_id": "s-1", "message": "날씨?"},
        )
        body = resp.json()

        assert body["answer"] == "좋은 날씨네요"
        assert body["was_summarized"] is True
        assert body["user_id"] == "u-1"
        assert body["session_id"] == "s-1"

    def test_chat_passes_request_to_use_case(self):
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = _ok_response()
        client = TestClient(_build_app(mock_uc))

        client.post(
            "/api/v1/conversation/chat",
            json={"user_id": "u-42", "session_id": "s-99", "message": "질문입니다"},
        )

        call_args = mock_uc.execute.call_args
        request_arg = call_args[0][0]
        assert request_arg.user_id == "u-42"
        assert request_arg.session_id == "s-99"
        assert request_arg.message == "질문입니다"

    def test_chat_missing_user_id_returns_422(self):
        mock_uc = AsyncMock()
        client = TestClient(_build_app(mock_uc))

        resp = client.post(
            "/api/v1/conversation/chat",
            json={"session_id": "s-1", "message": "질문"},
        )

        assert resp.status_code == 422

    def test_chat_missing_session_id_returns_422(self):
        mock_uc = AsyncMock()
        client = TestClient(_build_app(mock_uc))

        resp = client.post(
            "/api/v1/conversation/chat",
            json={"user_id": "u-1", "message": "질문"},
        )

        assert resp.status_code == 422

    def test_chat_missing_message_returns_422(self):
        mock_uc = AsyncMock()
        client = TestClient(_build_app(mock_uc))

        resp = client.post(
            "/api/v1/conversation/chat",
            json={"user_id": "u-1", "session_id": "s-1"},
        )

        assert resp.status_code == 422

    def test_chat_use_case_error_returns_500(self):
        mock_uc = AsyncMock()
        mock_uc.execute.side_effect = RuntimeError("DB 오류")
        client = TestClient(_build_app(mock_uc), raise_server_exceptions=False)

        resp = client.post(
            "/api/v1/conversation/chat",
            json={"user_id": "u-1", "session_id": "s-1", "message": "질문"},
        )

        assert resp.status_code == 500

    def test_chat_was_summarized_false_by_default(self):
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = _ok_response(was_summarized=False)
        client = TestClient(_build_app(mock_uc))

        resp = client.post(
            "/api/v1/conversation/chat",
            json={"user_id": "u-1", "session_id": "s-1", "message": "질문"},
        )
        body = resp.json()

        assert body["was_summarized"] is False
