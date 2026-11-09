"""GET /api/v1/agents/{agent_id}/document-template 라우터 테스트.

extractor-template-preview Design §8.2 B9–B10.
"""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes.agent_builder_router import (
    get_get_agent_document_template_use_case,
    router,
)
from src.application.agent_builder.get_agent_document_template_use_case import (
    AgentDocumentTemplateNotFoundError,
    AgentNotFoundError,
)
from src.application.agent_builder.schemas import (
    AgentDocumentTemplateResponse,
    SavedTemplateSlot,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.interfaces.dependencies.auth import get_current_user

PATH = "/api/v1/agents/agent-1/document-template"


def _fake_user() -> User:
    return User(
        email="owner@test.com",
        password_hash="hashed",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=7,
    )


def _response() -> AgentDocumentTemplateResponse:
    return AgentDocumentTemplateResponse(
        template_id="tpl-1",
        name="여신 승인 신청서",
        source_format="docx",
        html_skeleton="<p>{{borrower_name}}</p>",
        slots=[
            SavedTemplateSlot(
                key="borrower_name", label="차주명", slot_type="value",
                sample_value="홍길동",
            )
        ],
        samples_hidden=False,
        is_inherited=False,
        updated_at=datetime(2026, 11, 9, tzinfo=UTC),
    )


def _client(use_case, authenticated: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    if authenticated:
        app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_get_agent_document_template_use_case] = (
        lambda: use_case
    )
    return TestClient(app)


def _use_case(result=None, error: Exception | None = None):
    uc = MagicMock()
    uc.execute = AsyncMock(return_value=result, side_effect=error)
    return uc


class TestGetAgentDocumentTemplateRoute:
    def test_returns_template(self):
        uc = _use_case(result=_response())

        res = _client(uc).get(PATH)

        assert res.status_code == 200
        body = res.json()
        assert body["template_id"] == "tpl-1"
        assert body["name"] == "여신 승인 신청서"
        assert body["slots"][0]["label"] == "차주명"
        assert body["samples_hidden"] is False
        assert "source_file_ref" not in body
        args, kwargs = uc.execute.call_args
        assert args[0] == "agent-1"
        assert kwargs["viewer_user_id"] == "7"
        assert kwargs["viewer_role"] == "user"

    def test_permission_error_maps_to_403(self):
        uc = _use_case(error=PermissionError("양식 조회 권한이 없습니다"))

        res = _client(uc).get(PATH)

        assert res.status_code == 403
        assert res.json()["detail"] == "양식 조회 권한이 없습니다"

    def test_agent_not_found_maps_to_404(self):
        uc = _use_case(error=AgentNotFoundError("Agent not found: agent-1"))

        res = _client(uc).get(PATH)

        assert res.status_code == 404
        assert res.json()["detail"] == "Agent not found"

    def test_template_not_found_maps_to_404(self):
        uc = _use_case(
            error=AgentDocumentTemplateNotFoundError("Document template not found")
        )

        res = _client(uc).get(PATH)

        assert res.status_code == 404
        assert res.json()["detail"] == "Document template not found"

    def test_requires_authentication(self):
        res = _client(_use_case(result=_response()), authenticated=False).get(PATH)

        assert res.status_code == 401

    def test_route_is_registered(self):
        app = FastAPI()
        app.include_router(router)

        assert (
            app.url_path_for("get_agent_document_template", agent_id="agent-1")
            == PATH
        )
