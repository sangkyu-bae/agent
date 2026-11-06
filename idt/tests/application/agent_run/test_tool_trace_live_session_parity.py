"""실시간 payload 와 세션 API 응답의 tool_trace 동일성 (agent-run-tool-trace §8.1, Plan R4).

같은 기록을 두 경로(WS 리더 → payload / 세션 유스케이스 → REST 응답 직렬화)로 흘려
JSON 이 같은지 본다. 저장소만 대역이고 서비스·정책·스키마는 실물이다.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.agent_run_router import get_session_tool_traces_use_case, router
from src.application.agent_run.run_tool_trace import RunToolTraceService
from src.application.agent_run.use_cases.get_session_tool_traces_use_case import (
    GetSessionToolTracesUseCase,
)
from src.domain.agent_run.entities import AgentRun, AgentRunStep, ToolCall
from src.domain.agent_run.value_objects import (
    CostUsd,
    NodeType,
    RunId,
    RunStatus,
    StepStatus,
    TokenUsage,
)
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
from src.domain.tool_catalog.entity import ToolCatalogEntry
from src.infrastructure.agent_run.run_tool_trace_reader import (
    SessionScopedRunToolTraceReader,
)
from src.interfaces.dependencies.auth import get_current_user

T0 = datetime(2026, 11, 3, tzinfo=timezone.utc)
RUN = RunId("11111111-1111-1111-1111-111111111111")
SERVER = "6ea2f615-515e-4f65-aabe-388970dbafbe"
MCP_RUNTIME = f"mcp_{SERVER.replace('-', '_')}_list_inquiries"


def _step(id_, index, node_name, node_type, output=None, parent=None, depth=0):
    return AgentRunStep(
        id=id_, run_id=RUN, step_index=index, node_name=node_name, node_type=node_type,
        llm_model_id=None, status=StepStatus.SUCCESS, input_summary=None,
        output_summary=output, started_at=T0 + timedelta(seconds=index), ended_at=None,
        latency_ms=None, error_text=None, parent_step_id=parent, depth=depth,
    )


def _call(id_, step_id, tool_name, args, summary, status="SUCCESS", seconds=0):
    return ToolCall(
        id=id_, run_id=RUN, step_id=step_id, tool_name=tool_name, llm_model_id=None,
        arguments_json=args, result_summary=summary, result_json=None, token_usage=None,
        total_cost_usd=None, latency_ms=12, status=status, error_text=None,
        created_at=T0 + timedelta(seconds=seconds),
    )


# 실데이터 D1~D4 형태를 한 런에 섞는다.
STEPS = [
    _step("s1", 1, "supervisor", NodeType.SUPERVISOR, "위키와 문의 목록을 확인한다"),
    _step("w1", 2, "wiki_read_worker", NodeType.WORKER, "도구 호출 1회"),
    _step("sub", 3, "sub_agent_[멀티]_답변_작성자_1", NodeType.WORKER),
    _step("w2", 4, "list_worker", NodeType.WORKER, parent="sub", depth=1),
]
CALLS = [
    _call("t1", "w1", "wiki_read", {"article_id": "a1"},
          '{"content": "[위키 문서: 배포]\\n본문", "additional_kwargs": {}}', seconds=2),
    _call("t2", "w2", MCP_RUNTIME, {"arguments": {"board": "loan"}},
          '{"content": "Error executing tool list_inquiries: 1 validation error"}', seconds=4),
    _call("t3", None, "tavily_search", {"query": "금리"}, "가" * 1024, seconds=5),
]
CATALOG = [
    ToolCatalogEntry(id="e1", tool_id="internal:wiki_read", source="internal",
                     name="에이전트 위키 열람", description=""),
    ToolCatalogEntry(id="e2", tool_id=f"mcp:{SERVER}:list_inquiries", source="mcp",
                     name="list_inquiries", description=""),
]


def _service() -> RunToolTraceService:
    runs = MagicMock()
    runs.find_tool_calls_by_runs = AsyncMock(return_value={RUN.value: CALLS})
    runs.find_steps_by_runs = AsyncMock(return_value={RUN.value: STEPS})
    catalog = MagicMock()
    catalog.list_active = AsyncMock(return_value=CATALOG)
    return RunToolTraceService(runs, catalog, MagicMock(), max_items=50)


async def _live_payload() -> dict:
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=MagicMock())
    context.__aexit__ = AsyncMock(return_value=False)
    reader = SessionScopedRunToolTraceReader(
        MagicMock(return_value=context), lambda _: _service(), MagicMock(),
    )
    trace = await reader.load_for_run(RUN, "req")
    return trace.to_payload()


def _session_response() -> dict:
    def message(mid, role):
        return ConversationMessage(
            id=MessageId(mid), user_id=UserId("7"), session_id=SessionId("s1"),
            agent_id=AgentId("agent-1"), role=role, content="x",
            turn_index=TurnIndex(1), created_at=T0,
        )

    run = AgentRun(
        id=RUN, conversation_id="s1", user_id="7", agent_id="agent-1",
        llm_model_id=None, user_message_id=1, status=RunStatus.SUCCESS,
        langgraph_thread_id="t", langsmith_trace_id=None, langsmith_run_url=None,
        token_usage=TokenUsage(0, 0, 0), cost_usd=CostUsd(), llm_call_count=0,
        started_at=T0, ended_at=None, latency_ms=None, error_message=None,
        error_stack=None,
    )
    message_repo = MagicMock()
    message_repo.find_by_session = AsyncMock(
        return_value=[message(1, MessageRole.USER), message(2, MessageRole.ASSISTANT)],
    )
    run_repo = MagicMock()
    run_repo.find_latest_runs_by_user_messages = AsyncMock(return_value={1: run})
    use_case = GetSessionToolTracesUseCase(message_repo, run_repo, _service(), MagicMock())

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session_tool_traces_use_case] = lambda: use_case
    app.dependency_overrides[get_current_user] = lambda: User(
        email="u@test.com", password_hash="h", role=UserRole.USER,
        status=UserStatus.APPROVED, id=7,
    )
    body = TestClient(app).get(
        "/api/v1/conversations/agents/agent-1/sessions/s1/tool-traces",
    ).json()
    return body["items"][0]["tool_trace"]


@pytest.mark.asyncio
async def test_live_payload_equals_session_response() -> None:
    live = await _live_payload()
    assert live == _session_response()
    # 표본이 실제로 규칙을 지나갔는지 — 빈 결과끼리 같은 거짓 초록 방지.
    assert [(i["kind"], i["label"]) for i in live["items"]] == [
        ("reasoning", "판단"),
        ("tool", "에이전트 위키 열람"),
        ("tool", "list_inquiries"),
        ("tool", "tavily_search"),
    ]
    assert live["items"][2]["status"] == "failed"
    assert live["items"][2]["worker"] == "[멀티] 답변 작성자"
    assert live["items"][3]["output_truncated"] is True
