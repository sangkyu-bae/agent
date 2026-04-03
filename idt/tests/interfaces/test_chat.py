from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.interfaces import app


client = TestClient(app)


class TestChatEndpoint:
    def test_chat_returns_assistant_response(self) -> None:
        with patch("src.interfaces.chat_use_case.execute", new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = "Hello! How can I help you?"

            response = client.post(
                "/chat",
                json={
                    "user_id": "user-1",
                    "session_id": "session-1",
                    "message": "Hello",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert data["response"] == "Hello! How can I help you?"
        assert "session_id" in data
        assert data["session_id"] == "session-1"
        mock_execute.assert_called_once_with(
            user_id="user-1",
            session_id="session-1",
            message="Hello",
        )

    def test_chat_requires_user_id(self) -> None:
        response = client.post(
            "/chat",
            json={
                "session_id": "session-1",
                "message": "Hello",
            },
        )

        assert response.status_code == 422

    def test_chat_requires_message(self) -> None:
        response = client.post(
            "/chat",
            json={
                "user_id": "user-1",
                "session_id": "session-1",
            },
        )

        assert response.status_code == 422
