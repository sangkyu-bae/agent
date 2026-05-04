"""에이전트별 대화 히스토리 API 엔드포인트 테스트 (AGENT-CHAT-001)."""
from datetime import datetime
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.conversation_history_router import (
    get_history_use_case,
    router,
)
from src.domain.conversation.history_schemas import (
    AgentChatSummary,
    AgentListResponse,
    AgentMessageListResponse,
    AgentSessionListResponse,
    MessageItem,
    SessionSummary,
)


def _build_app(mock_uc) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_history_use_case] = lambda: mock_uc
    return app


class TestGetAgents:
    """TC-R1, TC-R2: GET /api/v1/conversations/agents"""

    def test_returns_200_with_agents(self):
        mock_uc = AsyncMock()
        mock_uc.get_agents_with_history.return_value = AgentListResponse(
            user_id="u-1",
            agents=[
                AgentChatSummary(
                    agent_id="super",
                    agent_name="일반 채팅",
                    session_count=5,
                    last_chat_at=datetime(2026, 4, 30, 10, 30),
                ),
                AgentChatSummary(
                    agent_id="a1b2c3d4",
                    agent_name="금융 분석 에이전트",
                    session_count=3,
                    last_chat_at=datetime(2026, 4, 29, 15, 0),
                ),
            ],
        )
        client = TestClient(_build_app(mock_uc))

        resp = client.get("/api/v1/conversations/agents?user_id=u-1")

        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == "u-1"
        assert len(body["agents"]) == 2
        assert body["agents"][0]["agent_id"] == "super"
        assert body["agents"][0]["agent_name"] == "일반 채팅"
        assert body["agents"][1]["agent_id"] == "a1b2c3d4"

    def test_missing_user_id_returns_422(self):
        mock_uc = AsyncMock()
        client = TestClient(_build_app(mock_uc))

        resp = client.get("/api/v1/conversations/agents")

        assert resp.status_code == 422


class TestGetAgentSessions:
    """TC-R3, TC-R4: GET /api/v1/conversations/agents/{agent_id}/sessions"""

    def test_returns_200_with_sessions(self):
        mock_uc = AsyncMock()
        mock_uc.get_sessions_by_agent.return_value = AgentSessionListResponse(
            user_id="u-1",
            agent_id="super",
            sessions=[
                SessionSummary(
                    session_id="s-abc",
                    message_count=8,
                    last_message="부동산 취득세 면제 조건이 뭔가요?",
                    last_message_at=datetime(2026, 4, 30, 10, 30),
                )
            ],
        )
        client = TestClient(_build_app(mock_uc))

        resp = client.get(
            "/api/v1/conversations/agents/super/sessions?user_id=u-1"
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == "u-1"
        assert body["agent_id"] == "super"
        assert len(body["sessions"]) == 1
        assert body["sessions"][0]["session_id"] == "s-abc"

    def test_empty_sessions_returns_200(self):
        mock_uc = AsyncMock()
        mock_uc.get_sessions_by_agent.return_value = AgentSessionListResponse(
            user_id="u-1",
            agent_id="unknown-agent",
            sessions=[],
        )
        client = TestClient(_build_app(mock_uc))

        resp = client.get(
            "/api/v1/conversations/agents/unknown-agent/sessions?user_id=u-1"
        )

        assert resp.status_code == 200
        assert resp.json()["sessions"] == []


class TestGetAgentSessionMessages:
    """TC-R5, TC-R6: GET /api/v1/conversations/agents/{agent_id}/sessions/{session_id}/messages"""

    def test_returns_200_with_messages(self):
        mock_uc = AsyncMock()
        mock_uc.get_messages_by_agent.return_value = AgentMessageListResponse(
            user_id="u-1",
            agent_id="super",
            session_id="s-abc",
            messages=[
                MessageItem(
                    id=1,
                    role="user",
                    content="안녕하세요",
                    turn_index=1,
                    created_at=datetime(2026, 4, 30, 9, 0),
                ),
                MessageItem(
                    id=2,
                    role="assistant",
                    content="안녕하세요! 무엇을 도와드릴까요?",
                    turn_index=2,
                    created_at=datetime(2026, 4, 30, 9, 0, 5),
                ),
            ],
        )
        client = TestClient(_build_app(mock_uc))

        resp = client.get(
            "/api/v1/conversations/agents/super/sessions/s-abc/messages?user_id=u-1"
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == "u-1"
        assert body["agent_id"] == "super"
        assert body["session_id"] == "s-abc"
        assert len(body["messages"]) == 2
        assert body["messages"][0]["role"] == "user"
        assert body["messages"][1]["role"] == "assistant"

    def test_empty_messages_returns_200(self):
        mock_uc = AsyncMock()
        mock_uc.get_messages_by_agent.return_value = AgentMessageListResponse(
            user_id="u-1",
            agent_id="super",
            session_id="no-msgs",
            messages=[],
        )
        client = TestClient(_build_app(mock_uc))

        resp = client.get(
            "/api/v1/conversations/agents/super/sessions/no-msgs/messages?user_id=u-1"
        )

        assert resp.status_code == 200
        assert resp.json()["messages"] == []
