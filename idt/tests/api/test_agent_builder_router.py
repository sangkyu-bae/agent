"""Agent Builder Router 단위 테스트 — TestClient + Mock UseCase."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.routes.agent_builder_router import (
    router,
    get_create_agent_use_case,
    get_update_agent_use_case,
    get_run_agent_use_case,
    get_get_agent_use_case,
    get_interview_use_case,
    get_load_mcp_tools_use_case,
    get_list_agents_use_case,
    get_delete_agent_use_case,
)
from src.application.agent_builder.schemas import (
    AgentDraftPreview,
    AgentSummary,
    CreateAgentResponse,
    ListAgentsResponse,
    GetAgentResponse,
    InterviewAnswerResponse,
    InterviewStartResponse,
    RunAgentResponse,
    UpdateAgentResponse,
    WorkerInfo,
)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _make_create_response() -> CreateAgentResponse:
    return CreateAgentResponse(
        agent_id=str(uuid.uuid4()),
        name="AI 뉴스 수집기",
        system_prompt="당신은 AI 뉴스 수집 에이전트입니다.",
        tool_ids=["tavily_search", "excel_export"],
        workers=[
            WorkerInfo(tool_id="tavily_search", worker_id="search_worker",
                       description="검색", sort_order=0),
        ],
        flow_hint="search 후 export",
        llm_model_id="model-1",
        visibility="private",
        department_id=None,
        temperature=0.70,
        created_at=_now_iso(),
    )


def _make_get_response(agent_id: str) -> GetAgentResponse:
    return GetAgentResponse(
        agent_id=agent_id,
        name="AI 뉴스 수집기",
        description="테스트 요청",
        system_prompt="프롬프트",
        tool_ids=["tavily_search"],
        workers=[WorkerInfo(tool_id="tavily_search", worker_id="search_worker",
                            description="검색", sort_order=0)],
        flow_hint="힌트",
        llm_model_id="model-1",
        status="active",
        visibility="private",
        department_id=None,
        temperature=0.70,
        owner_user_id="user-1",
        can_edit=True,
        can_delete=True,
        created_at=_now_iso(),
        updated_at=_now_iso(),
    )


def _make_update_response(agent_id: str) -> UpdateAgentResponse:
    return UpdateAgentResponse(
        agent_id=agent_id,
        name="수정된 이름",
        system_prompt="수정된 프롬프트",
        updated_at=_now_iso(),
    )


def _make_run_response(agent_id: str) -> RunAgentResponse:
    return RunAgentResponse(
        agent_id=agent_id,
        query="AI 뉴스 수집해줘",
        answer="AI 뉴스를 수집했습니다.",
        tools_used=["tavily_search"],
        request_id=str(uuid.uuid4()),
    )


def _make_fake_user():
    from src.domain.auth.entities import User, UserRole, UserStatus
    return User(
        email="test@test.com",
        password_hash="hashed",
        role=UserRole.ADMIN,
        status=UserStatus.APPROVED,
        id=1,
    )


def _make_client(overrides: dict) -> TestClient:
    from fastapi import FastAPI
    from src.interfaces.dependencies.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _make_fake_user
    for dep, override in overrides.items():
        app.dependency_overrides[dep] = override
    return TestClient(app)


# ── GET /tools ────────────────────────────────────────────────────


def _make_mock_load_mcp_uc(mcp_registrations=None):
    """LoadMCPToolsUseCase mock — list_meta returns empty by default."""
    uc = MagicMock()
    uc.list_meta = AsyncMock(return_value=mcp_registrations or [])
    return uc


class TestListTools:
    def test_list_tools_returns_200_and_four_tools(self):
        mock_uc = _make_mock_load_mcp_uc()
        client = _make_client({get_load_mcp_tools_use_case: lambda: mock_uc})
        resp = client.get("/api/v1/agents/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["tools"]) == 4  # 내부 도구 4개, MCP 없음

    def test_each_tool_has_required_fields(self):
        mock_uc = _make_mock_load_mcp_uc()
        client = _make_client({get_load_mcp_tools_use_case: lambda: mock_uc})
        resp = client.get("/api/v1/agents/tools")
        for tool in resp.json()["tools"]:
            assert "tool_id" in tool
            assert "name" in tool
            assert "description" in tool

    def test_list_tools_includes_mcp_tools(self):
        from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType
        from datetime import datetime
        mcp_reg = MCPServerRegistration(
            id="mcp-uuid-1", user_id="u1", name="External MCP Tool",
            description="An MCP tool", endpoint="https://mcp.example.com/sse",
            transport=MCPTransportType.SSE, input_schema=None, is_active=True,
            created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
        )
        mock_uc = _make_mock_load_mcp_uc(mcp_registrations=[mcp_reg])
        client = _make_client({get_load_mcp_tools_use_case: lambda: mock_uc})
        resp = client.get("/api/v1/agents/tools")
        assert resp.status_code == 200
        tools = resp.json()["tools"]
        assert len(tools) == 5  # 내부 4 + MCP 1
        tool_ids = [t["tool_id"] for t in tools]
        assert "mcp_mcp-uuid-1" in tool_ids


# ── POST /agents ──────────────────────────────────────────────────


class TestCreateAgent:
    def test_create_agent_returns_201(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=_make_create_response())
        client = _make_client({get_create_agent_use_case: lambda: mock_uc})

        resp = client.post("/api/v1/agents", json={
            "user_request": "AI 뉴스 검색하고 엑셀 저장해줘",
            "name": "AI 뉴스 수집기",
            "user_id": "user-1",
        })
        assert resp.status_code == 201

    def test_create_agent_response_has_system_prompt(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=_make_create_response())
        client = _make_client({get_create_agent_use_case: lambda: mock_uc})

        resp = client.post("/api/v1/agents", json={
            "user_request": "AI 뉴스 검색하고 엑셀 저장해줘",
            "name": "AI 뉴스 수집기",
            "user_id": "user-1",
        })
        data = resp.json()
        assert "system_prompt" in data
        assert data["system_prompt"] == "당신은 AI 뉴스 수집 에이전트입니다."

    def test_create_agent_missing_name_returns_422(self):
        client = _make_client({get_create_agent_use_case: lambda: MagicMock()})
        resp = client.post("/api/v1/agents", json={
            "user_request": "요청",
            "user_id": "user-1",
        })
        assert resp.status_code == 422


# ── GET /agents/{id} ──────────────────────────────────────────────


class TestGetAgent:
    def test_get_agent_returns_200(self):
        agent_id = str(uuid.uuid4())
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=_make_get_response(agent_id))
        client = _make_client({get_get_agent_use_case: lambda: mock_uc})

        resp = client.get(f"/api/v1/agents/{agent_id}")
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == agent_id

    def test_get_agent_not_found_returns_404(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=None)
        client = _make_client({get_get_agent_use_case: lambda: mock_uc})

        resp = client.get("/api/v1/agents/non-existent")
        assert resp.status_code == 404


# ── PATCH /agents/{id} ───────────────────────────────────────────


class TestUpdateAgent:
    def test_update_agent_returns_200(self):
        agent_id = str(uuid.uuid4())
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=_make_update_response(agent_id))
        client = _make_client({get_update_agent_use_case: lambda: mock_uc})

        resp = client.patch(f"/api/v1/agents/{agent_id}", json={
            "system_prompt": "수정된 프롬프트",
        })
        assert resp.status_code == 200
        assert resp.json()["system_prompt"] == "수정된 프롬프트"

    def test_update_agent_policy_error_returns_422(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(side_effect=ValueError("비활성화된 에이전트"))
        client = _make_client({get_update_agent_use_case: lambda: mock_uc})

        resp = client.patch("/api/v1/agents/some-id", json={"system_prompt": "새 프롬프트"})
        assert resp.status_code == 422

    def test_update_agent_not_found_returns_404(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(side_effect=ValueError("찾을 수 없습니다"))
        client = _make_client({get_update_agent_use_case: lambda: mock_uc})

        resp = client.patch("/api/v1/agents/non-existent", json={"name": "새 이름"})
        assert resp.status_code == 404


# ── POST /agents/{id}/run ─────────────────────────────────────────


class TestRunAgent:
    def test_run_agent_returns_200(self):
        agent_id = str(uuid.uuid4())
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=_make_run_response(agent_id))
        client = _make_client({get_run_agent_use_case: lambda: mock_uc})

        resp = client.post(f"/api/v1/agents/{agent_id}/run", json={
            "query": "AI 뉴스 수집해줘",
            "user_id": "user-1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == agent_id
        assert data["answer"] == "AI 뉴스를 수집했습니다."

    def test_run_agent_not_found_returns_404(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(side_effect=ValueError("찾을 수 없습니다"))
        client = _make_client({get_run_agent_use_case: lambda: mock_uc})

        resp = client.post("/api/v1/agents/non-existent/run", json={
            "query": "쿼리", "user_id": "user-1",
        })
        assert resp.status_code == 404


# ── POST /agents/interview ────────────────────────────────────────


class TestStartInterview:
    def test_start_interview_returns_201_with_session_id(self):
        mock_uc = MagicMock()
        mock_uc.start = AsyncMock(
            return_value=InterviewStartResponse(
                session_id="sess-1",
                questions=["어떤 주제?", "저장 경로?", "몇 개?"],
            )
        )
        client = _make_client({get_interview_use_case: lambda: mock_uc})

        resp = client.post("/api/v1/agents/interview", json={
            "user_request": "AI 뉴스 수집 에이전트 만들어줘",
            "name": "AI 뉴스 수집기",
            "user_id": "user-1",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["session_id"] == "sess-1"
        assert len(data["questions"]) == 3

    def test_start_interview_missing_fields_returns_422(self):
        client = _make_client({get_interview_use_case: lambda: MagicMock()})
        resp = client.post("/api/v1/agents/interview", json={"user_request": "AI 뉴스"})
        assert resp.status_code == 422


# ── POST /agents/interview/{session_id}/answer ────────────────────


class TestAnswerInterview:
    def test_answer_returns_reviewing_status(self):
        mock_uc = MagicMock()
        mock_uc.answer = AsyncMock(
            return_value=InterviewAnswerResponse(
                session_id="sess-1",
                status="reviewing",
                preview=AgentDraftPreview(
                    tool_ids=["tavily_search"],
                    workers=[WorkerInfo(tool_id="tavily_search", worker_id="search_worker",
                                        description="검색", sort_order=0)],
                    flow_hint="search 후 export",
                    system_prompt="당신은 AI 뉴스 수집 에이전트입니다.",
                ),
            )
        )
        client = _make_client({get_interview_use_case: lambda: mock_uc})

        resp = client.post("/api/v1/agents/interview/sess-1/answer",
                           json={"answers": ["OpenAI 뉴스", "/data/news", "10개"]})
        assert resp.status_code == 200
        assert resp.json()["status"] == "reviewing"

    def test_answer_returns_questioning_status(self):
        mock_uc = MagicMock()
        mock_uc.answer = AsyncMock(
            return_value=InterviewAnswerResponse(
                session_id="sess-1",
                status="questioning",
                questions=["저장 경로는?", "몇 개?"],
            )
        )
        client = _make_client({get_interview_use_case: lambda: mock_uc})

        resp = client.post("/api/v1/agents/interview/sess-1/answer",
                           json={"answers": ["OpenAI 뉴스만"]})
        assert resp.status_code == 200
        assert resp.json()["status"] == "questioning"

    def test_answer_session_not_found_returns_404(self):
        mock_uc = MagicMock()
        mock_uc.answer = AsyncMock(side_effect=ValueError("인터뷰 세션을 찾을 수 없습니다"))
        client = _make_client({get_interview_use_case: lambda: mock_uc})

        resp = client.post("/api/v1/agents/interview/bad-id/answer",
                           json={"answers": ["답변"]})
        assert resp.status_code == 404


# ── POST /agents/interview/{session_id}/finalize ──────────────────


class TestFinalizeInterview:
    def test_finalize_returns_201(self):
        mock_uc = MagicMock()
        mock_uc.finalize = AsyncMock(return_value=_make_create_response())
        client = _make_client({get_interview_use_case: lambda: mock_uc})

        resp = client.post("/api/v1/agents/interview/sess-1/finalize", json={})
        assert resp.status_code == 201
        assert "agent_id" in resp.json()

    def test_finalize_session_not_found_returns_404(self):
        mock_uc = MagicMock()
        mock_uc.finalize = AsyncMock(
            side_effect=ValueError("인터뷰 세션을 찾을 수 없습니다: sess-99")
        )
        client = _make_client({get_interview_use_case: lambda: mock_uc})

        resp = client.post("/api/v1/agents/interview/sess-99/finalize", json={})
        assert resp.status_code == 404

    def test_finalize_draft_not_ready_returns_422(self):
        mock_uc = MagicMock()
        mock_uc.finalize = AsyncMock(
            side_effect=ValueError("아직 초안이 생성되지 않았습니다. 먼저 답변을 완료해주세요.")
        )
        client = _make_client({get_interview_use_case: lambda: mock_uc})

        resp = client.post("/api/v1/agents/interview/sess-1/finalize", json={})
        assert resp.status_code == 422


# ── GET /agents (list) ────────────────────────────────────────────


def _make_list_response() -> ListAgentsResponse:
    return ListAgentsResponse(
        agents=[
            AgentSummary(
                agent_id="a-1",
                name="테스트 에이전트",
                description="설명",
                visibility="public",
                owner_user_id="1",
                temperature=0.70,
                can_edit=True,
                can_delete=True,
                created_at=_now_iso(),
            )
        ],
        total=1,
        page=1,
        size=20,
    )


class TestListAgents:
    def test_list_agents_returns_200(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=_make_list_response())
        client = _make_client({get_list_agents_use_case: lambda: mock_uc})
        resp = client.get("/api/v1/agents?scope=all")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["agents"]) == 1

    def test_list_agents_with_search(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            return_value=ListAgentsResponse(agents=[], total=0, page=1, size=20)
        )
        client = _make_client({get_list_agents_use_case: lambda: mock_uc})
        resp = client.get("/api/v1/agents?search=뉴스&scope=mine")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ── DELETE /agents/{id} ──────────────────────────────────────────


class TestDeleteAgent:
    def test_delete_agent_returns_204(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=None)
        client = _make_client({get_delete_agent_use_case: lambda: mock_uc})
        resp = client.delete("/api/v1/agents/agent-1")
        assert resp.status_code == 204

    def test_delete_agent_not_found_returns_404(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            side_effect=ValueError("에이전트를 찾을 수 없습니다: agent-99")
        )
        client = _make_client({get_delete_agent_use_case: lambda: mock_uc})
        resp = client.delete("/api/v1/agents/agent-99")
        assert resp.status_code == 404

    def test_delete_agent_forbidden_returns_403(self):
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            side_effect=PermissionError("삭제 권한이 없습니다")
        )
        client = _make_client({get_delete_agent_use_case: lambda: mock_uc})
        resp = client.delete("/api/v1/agents/agent-1")
        assert resp.status_code == 403
