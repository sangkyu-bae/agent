"""middleware_agent_router API 테스트."""
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.middleware_agent_router import (
    router,
    get_create_use_case,
    get_get_use_case,
    get_run_use_case,
    get_update_use_case,
)
from src.application.middleware_agent.schemas import (
    CreateMiddlewareAgentResponse,
    GetMiddlewareAgentResponse,
    RunMiddlewareAgentResponse,
)


def _make_app(create_uc=None, get_uc=None, run_uc=None, update_uc=None) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    if create_uc:
        app.dependency_overrides[get_create_use_case] = lambda: create_uc
    if get_uc:
        app.dependency_overrides[get_get_use_case] = lambda: get_uc
    if run_uc:
        app.dependency_overrides[get_run_use_case] = lambda: run_uc
    if update_uc:
        app.dependency_overrides[get_update_use_case] = lambda: update_uc
    return app


class TestMiddlewareAgentRouter:

    def test_get_tools_returns_list(self):
        app = _make_app()
        client = TestClient(app)
        resp = client.get("/api/v2/agents/tools")
        assert resp.status_code == 200
        assert "tools" in resp.json()

    def test_create_agent_success(self):
        mock_uc = AsyncMock()
        mock_uc.execute = AsyncMock(return_value=CreateMiddlewareAgentResponse(
            agent_id="uuid-1", name="테스트", middleware_count=0, status="active"
        ))
        app = _make_app(create_uc=mock_uc)
        client = TestClient(app)

        payload = {
            "user_id": "user-1",
            "name": "테스트",
            "description": "desc",
            "system_prompt": "prompt",
            "model_name": "gpt-4o",
            "tool_ids": ["internal_document_search"],
            "middleware": [],
            "request_id": "req-1",
        }
        resp = client.post("/api/v2/agents", json=payload)
        assert resp.status_code == 201
        assert resp.json()["agent_id"] == "uuid-1"

    def test_get_agent_success(self):
        mock_uc = AsyncMock()
        mock_uc.execute = AsyncMock(return_value=GetMiddlewareAgentResponse(
            agent_id="uuid-1",
            name="테스트",
            description="desc",
            system_prompt="prompt",
            model_name="gpt-4o",
            tool_ids=["internal_document_search"],
            middleware=[],
            status="active",
        ))
        app = _make_app(get_uc=mock_uc)
        client = TestClient(app)
        resp = client.get("/api/v2/agents/uuid-1")
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "uuid-1"

    def test_run_agent_success(self):
        mock_uc = AsyncMock()
        mock_uc.execute = AsyncMock(return_value=RunMiddlewareAgentResponse(
            answer="분석 결과",
            tools_used=["internal_document_search"],
            middleware_applied=["pii"],
        ))
        app = _make_app(run_uc=mock_uc)
        client = TestClient(app)
        resp = client.post("/api/v2/agents/uuid-1/run", json={"query": "분석해줘", "request_id": "req-1"})
        assert resp.status_code == 200
        assert resp.json()["answer"] == "분석 결과"

    def test_update_agent_success(self):
        mock_uc = AsyncMock()
        mock_uc.execute = AsyncMock(return_value=GetMiddlewareAgentResponse(
            agent_id="uuid-1",
            name="테스트",
            description="desc",
            system_prompt="new prompt",
            model_name="gpt-4o",
            tool_ids=["internal_document_search"],
            middleware=[],
            status="active",
        ))
        app = _make_app(update_uc=mock_uc)
        client = TestClient(app)
        resp = client.patch("/api/v2/agents/uuid-1", json={"system_prompt": "new prompt", "request_id": "req-1"})
        assert resp.status_code == 200
        assert resp.json()["system_prompt"] == "new prompt"
