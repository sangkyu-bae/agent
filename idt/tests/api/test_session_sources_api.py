"""GET /api/v1/conversations/agents/{agent_id}/sessions/{session_id}/sources.

agent-run-source-citations §4.2 / §8.2 L1. 라우트는 정적 검증 대신 실요청으로 본다.
"""
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.agent_run_router import get_session_sources_use_case, router
from src.application.agent_run.use_cases.get_session_sources_use_case import (
    MessageSources,
    SessionSourcesDto,
)
from src.domain.agent_run.source_policy import RunSourceItem, SourceKind
from src.domain.auth.entities import User, UserRole, UserStatus
from src.interfaces.dependencies.auth import get_current_user

URL = "/api/v1/conversations/agents/agent-1/sessions/s1/sources"
WEB = RunSourceItem(SourceKind.WEB, "금리", "발췌", "https://a.example", "https://a.example")
DOC = RunSourceItem(SourceKind.DOCUMENT, "a.pdf", "본문", "doc-1")


def _client(use_case: MagicMock, *, authenticated: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session_sources_use_case] = lambda: use_case
    if authenticated:
        app.dependency_overrides[get_current_user] = lambda: User(
            email="u@test.com", password_hash="h", role=UserRole.USER,
            status=UserStatus.APPROVED, id=7,
        )
    return TestClient(app)


def _use_case(items: list[MessageSources]) -> MagicMock:
    use_case = MagicMock()
    use_case.execute = AsyncMock(return_value=SessionSourcesDto("s1", items))
    return use_case


def test_returns_sources_per_assistant_message_for_current_user() -> None:
    use_case = _use_case([MessageSources(102, [DOC, WEB])])

    response = _client(use_case).get(URL, params={"user_id": "999"})

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "s1",
        "items": [{
            "message_id": 102,
            "sources": [
                {"kind": "document", "source": "a.pdf", "content": "본문", "chunk_id": "doc-1"},
                {"kind": "web", "source": "금리", "content": "발췌",
                 "chunk_id": "https://a.example", "url": "https://a.example"},
            ],
        }],
    }
    # 쿼리의 user_id 는 무시하고 토큰의 사용자로만 조회한다 (Design §7).
    assert use_case.execute.await_args.kwargs["user_id"] == "7"
    assert use_case.execute.await_args.kwargs["agent_id"] == "agent-1"
    assert use_case.execute.await_args.kwargs["session_id"] == "s1"


def test_empty_session_is_200_with_no_items() -> None:
    response = _client(_use_case([])).get(URL)
    assert (response.status_code, response.json()) == (200, {"session_id": "s1", "items": []})


def test_unauthenticated_is_401() -> None:
    response = _client(_use_case([]), authenticated=False).get(URL)
    assert response.status_code == 401


def test_sources_failure_is_200_with_no_items() -> None:
    """L1-6 — 실제 유스케이스로 근거 조립이 실패해도 200 빈 목록."""
    from datetime import datetime, timezone

    from src.application.agent_run.use_cases.get_session_sources_use_case import (
        GetSessionSourcesUseCase,
    )
    from src.domain.agent_run.entities import AgentRun
    from src.domain.agent_run.value_objects import CostUsd, RunId, RunStatus, TokenUsage
    from src.domain.conversation.entities import (
        AgentId, ConversationMessage, MessageId, MessageRole, SessionId, TurnIndex, UserId,
    )

    now = datetime(2026, 11, 3, tzinfo=timezone.utc)

    def message(mid: int, role: MessageRole) -> ConversationMessage:
        return ConversationMessage(
            id=MessageId(mid), user_id=UserId("7"), session_id=SessionId("s1"),
            agent_id=AgentId("agent-1"), role=role, content="x",
            turn_index=TurnIndex(1), created_at=now,
        )

    run = AgentRun(
        id=RunId("11111111-1111-1111-1111-111111111111"), conversation_id="s1",
        user_id="7", agent_id="agent-1", llm_model_id=None, user_message_id=1,
        status=RunStatus.SUCCESS, langgraph_thread_id="t", langsmith_trace_id=None,
        langsmith_run_url=None, token_usage=TokenUsage(0, 0, 0), cost_usd=CostUsd(),
        llm_call_count=0, started_at=now, ended_at=None, latency_ms=None,
        error_message=None, error_stack=None,
    )
    message_repo = MagicMock()
    message_repo.find_by_session = AsyncMock(
        return_value=[message(1, MessageRole.USER), message(2, MessageRole.ASSISTANT)],
    )
    run_repo = MagicMock()
    run_repo.find_latest_runs_by_user_messages = AsyncMock(return_value={1: run})
    sources = MagicMock()
    sources.build_for_runs = AsyncMock(side_effect=RuntimeError("boom"))
    use_case = GetSessionSourcesUseCase(message_repo, run_repo, sources, MagicMock())

    response = _client(use_case).get(URL)

    assert (response.status_code, response.json()) == (200, {"session_id": "s1", "items": []})


def test_response_has_no_internal_fields() -> None:
    body = _client(_use_case([MessageSources(1, [DOC])])).get(URL).text
    for key in ("metadata_json", "arguments_json", "score", "morph_text"):
        assert key not in body
