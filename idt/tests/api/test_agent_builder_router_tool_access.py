"""에이전트 생성·수정 라우터의 TOOL_ACCESS_DENIED 403 매핑 (tool-access-control §4.2)."""
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.agent_builder_router import (
    get_create_agent_use_case,
    get_update_agent_use_case,
    router,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.tool_access.exceptions import ToolAccessDeniedError
from src.interfaces.dependencies.auth import get_current_user

DENIED = "internal:python_code_executor"


def _client(create_uc=None, update_uc=None) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: User(
        email="u@t", password_hash="h", role=UserRole.USER, status=UserStatus.APPROVED, id=2
    )
    if create_uc is not None:
        app.dependency_overrides[get_create_agent_use_case] = lambda: create_uc
    if update_uc is not None:
        app.dependency_overrides[get_update_agent_use_case] = lambda: update_uc
    return TestClient(app)


def _failing(exc):
    uc = MagicMock()
    uc.execute = AsyncMock(side_effect=exc)
    return uc


def _assert_denied(res):
    assert res.status_code == 403
    detail = res.json()["detail"]
    assert detail["code"] == "TOOL_ACCESS_DENIED"
    assert detail["tool_ids"] == [DENIED]


def test_create_maps_tool_access_denied():
    res = _client(create_uc=_failing(ToolAccessDeniedError([DENIED]))).post(
        "/api/v1/agents",
        json={"user_request": "r", "name": "n", "system_prompt": "p", "tool_ids": [DENIED]},
    )
    _assert_denied(res)


def test_update_maps_tool_access_denied():
    res = _client(update_uc=_failing(ToolAccessDeniedError([DENIED]))).patch(
        "/api/v1/agents/a1", json={"tool_ids": [DENIED]}
    )
    _assert_denied(res)


def test_other_permission_error_keeps_plain_detail():
    res = _client(update_uc=_failing(PermissionError("수정 권한이 없습니다"))).patch(
        "/api/v1/agents/a1", json={"name": "x"}
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "수정 권한이 없습니다"
