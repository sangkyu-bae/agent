"""GET /api/v1/conversations/agents/{agent_id}/sessions/{session_id}/tool-traces.

agent-run-tool-trace §4.2 / §8.2 L1. 라우트는 정적 검증 대신 실요청으로 본다.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.agent_run_router import get_session_tool_traces_use_case, router
from src.application.agent_run.run_tool_trace import RunToolTraceService
from src.application.agent_run.use_cases.get_session_tool_traces_use_case import (
    GetSessionToolTracesUseCase,
    MessageToolTrace,
    SessionToolTracesDto,
)
from src.domain.agent_run.entities import AgentRun, ToolCall
from src.domain.agent_run.tool_trace_policy import (
    ToolTrace,
    ToolTraceItem,
    ToolTraceKind,
    ToolTraceSource,
    ToolTraceStatus,
)
from src.domain.agent_run.value_objects import CostUsd, RunId, RunStatus, TokenUsage
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.conversation.entities import (
    AgentId,
    ConversationMessage,
    MessageId,
    MessageRole,
    SessionId,
    TurnIndex,
    UserId,
)
from src.interfaces.dependencies.auth import get_current_user

URL = "/api/v1/conversations/agents/agent-1/sessions/s1/tool-traces"
T0 = datetime(2026, 11, 3, tzinfo=timezone.utc)
RUN = "11111111-1111-1111-1111-111111111111"

TRACE = ToolTrace(items=[
    ToolTraceItem(seq=1, kind=ToolTraceKind.REASONING, label="판단", text="위키를 읽는다"),
    ToolTraceItem(
        seq=2, kind=ToolTraceKind.TOOL, label="list_inquiries", source=ToolTraceSource.MCP,
        status=ToolTraceStatus.FAILED, duration_ms=41, input={"board": "loan"},
        error="Error executing tool list_inquiries",
    ),
], omitted_count=1)


def _client(use_case, *, authenticated: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session_tool_traces_use_case] = lambda: use_case
    if authenticated:
        app.dependency_overrides[get_current_user] = lambda: User(
            email="u@test.com", password_hash="h", role=UserRole.USER,
            status=UserStatus.APPROVED, id=7,
        )
    return TestClient(app)


def _stub(items: list[MessageToolTrace]) -> MagicMock:
    use_case = MagicMock()
    use_case.execute = AsyncMock(return_value=SessionToolTracesDto("s1", items))
    return use_case


def test_returns_trace_per_assistant_message_for_current_user() -> None:
    use_case = _stub([MessageToolTrace(102, TRACE)])

    response = _client(use_case).get(URL, params={"user_id": "999"})

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "s1",
        "items": [{
            "message_id": 102,
            "tool_trace": {
                "omitted_count": 1,
                "items": [
                    {"seq": 1, "kind": "reasoning", "label": "판단", "text": "위키를 읽는다"},
                    {"seq": 2, "kind": "tool", "label": "list_inquiries", "source": "mcp",
                     "status": "failed", "duration_ms": 41, "input": {"board": "loan"},
                     "error": "Error executing tool list_inquiries"},
                ],
            },
        }],
    }
    # 쿼리의 user_id 는 무시하고 토큰 사용자로만 조회한다 (Design §7).
    kwargs = use_case.execute.await_args.kwargs
    assert (kwargs["user_id"], kwargs["agent_id"], kwargs["session_id"]) == ("7", "agent-1", "s1")


def test_empty_session_is_200_with_no_items() -> None:
    response = _client(_stub([])).get(URL)
    assert (response.status_code, response.json()) == (200, {"session_id": "s1", "items": []})


def test_unauthenticated_is_401() -> None:
    assert _client(_stub([]), authenticated=False).get(URL).status_code == 401


def _message(mid: int, role: MessageRole) -> ConversationMessage:
    return ConversationMessage(
        id=MessageId(mid), user_id=UserId("7"), session_id=SessionId("s1"),
        agent_id=AgentId("agent-1"), role=role, content="x", turn_index=TurnIndex(1),
        created_at=T0,
    )


def _run(user_id: str = "7") -> AgentRun:
    return AgentRun(
        id=RunId(RUN), conversation_id="s1", user_id=user_id, agent_id="agent-1",
        llm_model_id=None, user_message_id=1, status=RunStatus.SUCCESS,
        langgraph_thread_id="t", langsmith_trace_id=None, langsmith_run_url=None,
        token_usage=TokenUsage(0, 0, 0), cost_usd=CostUsd(), llm_call_count=0,
        started_at=T0, ended_at=None, latency_ms=None, error_message=None,
        error_stack=None,
    )


def _real_use_case(run: AgentRun, tool_calls_error: Exception | None = None):
    """실제 유스케이스·서비스·정책으로 조립하고 저장소만 대역으로 둔다."""
    message_repo = MagicMock()
    message_repo.find_by_session = AsyncMock(
        return_value=[_message(1, MessageRole.USER), _message(2, MessageRole.ASSISTANT)],
    )
    run_repo = MagicMock()
    run_repo.find_latest_runs_by_user_messages = AsyncMock(return_value={1: run})
    call = ToolCall(
        id="t1", run_id=RunId(RUN), step_id=None, tool_name="wiki_read",
        llm_model_id=None, arguments_json={"article_id": "a1"}, result_summary="본문",
        result_json=None, token_usage=None, total_cost_usd=None, latency_ms=5,
        status="SUCCESS", error_text=None, created_at=T0,
    )
    run_repo.find_tool_calls_by_runs = AsyncMock(
        return_value={RUN: [call]}, side_effect=tool_calls_error,
    )
    run_repo.find_steps_by_runs = AsyncMock(return_value={})
    catalog = MagicMock()
    catalog.list_active = AsyncMock(return_value=[])
    service = RunToolTraceService(run_repo, catalog, MagicMock(), max_items=50)
    return GetSessionToolTracesUseCase(message_repo, run_repo, service, MagicMock()), run_repo


def test_real_use_case_returns_trace_with_fixed_query_count() -> None:
    use_case, run_repo = _real_use_case(_run())
    body = _client(use_case).get(URL).json()
    assert body["items"][0]["message_id"] == 2
    assert body["items"][0]["tool_trace"]["items"][0]["label"] == "wiki_read"
    assert run_repo.find_tool_calls_by_runs.await_count == 1
    assert run_repo.find_steps_by_runs.await_count == 1


def test_other_users_run_is_200_with_no_items() -> None:
    """L1-2 — 같은 세션 id 라도 타인 런은 내보내지 않는다."""
    use_case, run_repo = _real_use_case(_run(user_id="8"))
    response = _client(use_case).get(URL)
    assert (response.status_code, response.json()) == (200, {"session_id": "s1", "items": []})
    run_repo.find_tool_calls_by_runs.assert_not_awaited()


def test_storage_failure_is_200_with_no_items() -> None:
    """L1-5 — 내역 조회 실패는 히스토리를 막지 않는다."""
    use_case, _ = _real_use_case(_run(), tool_calls_error=RuntimeError("db"))
    response = _client(use_case).get(URL)
    assert (response.status_code, response.json()) == (200, {"session_id": "s1", "items": []})
