"""Agent Composer Router 단위 테스트 — TestClient + Mock UseCase."""
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.agent_composer.schemas import (
    ComposeAgentDraftResponse,
    MissingCapabilityDto,
)


def _make_fake_user():
    from src.domain.auth.entities import User, UserRole, UserStatus
    return User(
        email="user@test.com",
        password_hash="hashed",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=1,
    )


def _make_client(overrides: dict) -> TestClient:
    from src.api.routes.agent_composer_router import router
    from src.interfaces.dependencies.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _make_fake_user
    for dep, override in overrides.items():
        app.dependency_overrides[dep] = override
    return TestClient(app)


def _draft_response() -> ComposeAgentDraftResponse:
    return ComposeAgentDraftResponse(
        coverage="full",
        name_suggestion="검색 도우미",
        system_prompt="당신은 검색 에이전트입니다.",
        tool_ids=["tavily_search"],
        workers=[],
        flow_hint="tavily_search",
        llm_model_id="model-default",
        temperature=0.70,
        missing_capabilities=[],
        notes="",
    )


class TestComposeAgent:
    def test_compose_returns_200_with_draft(self):
        from src.api.routes.agent_composer_router import get_compose_agent_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=_draft_response())
        client = _make_client({get_compose_agent_use_case: lambda: mock_uc})
        resp = client.post(
            "/api/v1/agents/compose",
            json={"user_request": "웹 검색하는 에이전트 만들어줘"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["coverage"] == "full"
        assert body["tool_ids"] == ["tavily_search"]

    def test_compose_coverage_none(self):
        from src.api.routes.agent_composer_router import get_compose_agent_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            return_value=ComposeAgentDraftResponse(
                coverage="none",
                missing_capabilities=[
                    MissingCapabilityDto(
                        capability="ERP 조회",
                        reason="매칭 도구 없음",
                        suggestion="ERP MCP 등록 필요",
                    )
                ],
                notes="현재 도구로는 불가능합니다.",
            )
        )
        client = _make_client({get_compose_agent_use_case: lambda: mock_uc})
        resp = client.post(
            "/api/v1/agents/compose", json={"user_request": "ERP 조회 에이전트"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["coverage"] == "none"
        assert body["tool_ids"] == []
        assert body["missing_capabilities"][0]["capability"] == "ERP 조회"

    def test_compose_user_request_too_long_returns_422(self):
        from src.api.routes.agent_composer_router import get_compose_agent_use_case
        mock_uc = MagicMock()
        client = _make_client({get_compose_agent_use_case: lambda: mock_uc})
        resp = client.post(
            "/api/v1/agents/compose", json={"user_request": "가" * 1001}
        )
        assert resp.status_code == 422
        mock_uc.execute.assert_not_called()

    def test_compose_value_error_returns_422(self):
        from src.api.routes.agent_composer_router import get_compose_agent_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            side_effect=ValueError("LLM 모델을 찾을 수 없습니다: ghost")
        )
        client = _make_client({get_compose_agent_use_case: lambda: mock_uc})
        resp = client.post(
            "/api/v1/agents/compose",
            json={"user_request": "검색", "llm_model_id": "ghost"},
        )
        assert resp.status_code == 422
        assert "LLM 모델" in resp.json()["detail"]
