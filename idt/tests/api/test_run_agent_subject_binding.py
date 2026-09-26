"""POST /api/v1/agents/{id}/run — 실행 주체는 토큰 사용자로 강제한다.

mcp-identity-header Check G-1 (Critical): body.user_id 는 신원 헤더 주체와
승인 requested_by 로 쓰인다. 호출자가 남의 ID 를 넣으면 그 사람 메일함 토큰이
발급되므로, create_agent 와 같이 토큰 사용자로 덮어쓴다 (기존 클라이언트 호환).
"""
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.agent_builder_router import get_run_agent_use_case, router
from src.domain.agent_run.auth_context import AuthContext
from src.interfaces.dependencies.auth import get_auth_context


def _auth(user_id: int) -> AuthContext:
    return AuthContext(
        user_id=user_id, display_name="u", role="user",
        primary_department_id=None, primary_department_name=None,
        department_ids=(), department_names=(), permissions=frozenset(),
    )


def _client(uc, token_user: int) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_auth_context] = lambda: _auth(token_user)
    app.dependency_overrides[get_run_agent_use_case] = lambda: uc
    return TestClient(app)


def _uc():
    uc = MagicMock()
    uc.execute = AsyncMock(return_value={
        "agent_id": "ag1", "query": "q", "answer": "a", "tools_used": [],
        "request_id": "r", "session_id": "s",
    })
    return uc


class TestRunSubjectBinding:
    def test_본문의_다른_user_id는_토큰_사용자로_덮어쓴다(self):
        uc = _uc()
        _client(uc, token_user=7).post(
            "/api/v1/agents/ag1/run", json={"query": "메일 보여줘", "user_id": "8"}
        )
        body = uc.execute.call_args.args[1]
        assert body.user_id == "7"
        assert uc.execute.call_args.kwargs["viewer_user_id"] == "7"

    def test_일치하면_그대로(self):
        uc = _uc()
        _client(uc, token_user=7).post(
            "/api/v1/agents/ag1/run", json={"query": "q", "user_id": "7"}
        )
        assert uc.execute.call_args.args[1].user_id == "7"
