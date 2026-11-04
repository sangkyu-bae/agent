"""Admin Tool Access Router 테스트 — TestClient + Mock UseCase.

Design Ref: tool-access-control §4.1, §4.2, §8.2 L1-1~5
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.admin_tool_access_router import (
    get_default_tool_access_use_case,
    get_department_tool_access_use_case,
    get_user_tool_access_use_case,
    router,
)
from src.application.tool_access.schemas import (
    DefaultToolAccessResponse,
    DepartmentToolAccessResponse,
    InheritedToolAccessResponse,
    ToolGrantSourceResponse,
    UserToolAccessResponse,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.tool_access.exceptions import UnknownToolIdsError
from src.interfaces.dependencies.auth import get_current_user

A = "internal:excel_export"


def _user(role: UserRole, uid: int) -> User:
    return User(email="x@t", password_hash="h", role=role, status=UserStatus.APPROVED, id=uid)


def _client(current_user: User | None, **ucs) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    if current_user is not None:
        app.dependency_overrides[get_current_user] = lambda: current_user
    mapping = {
        "default": get_default_tool_access_use_case,
        "department": get_department_tool_access_use_case,
        "user": get_user_tool_access_use_case,
    }
    for key, uc in ucs.items():
        app.dependency_overrides[mapping[key]] = (lambda u: (lambda: u))(uc)
    return TestClient(app)


def _uc(get=None, replace=None):
    uc = MagicMock()
    uc.get = AsyncMock(return_value=get) if not isinstance(get, Exception) else AsyncMock(side_effect=get)
    uc.replace = (
        AsyncMock(return_value=replace) if not isinstance(replace, Exception)
        else AsyncMock(side_effect=replace)
    )
    return uc


ADMIN = _user(UserRole.ADMIN, 1)
USER = _user(UserRole.USER, 2)

PATHS = [
    ("get", "/api/v1/admin/tool-access/default"),
    ("put", "/api/v1/admin/tool-access/default"),
    ("get", "/api/v1/admin/tool-access/departments/d1"),
    ("put", "/api/v1/admin/tool-access/departments/d1"),
    ("get", "/api/v1/admin/tool-access/users/12"),
    ("put", "/api/v1/admin/tool-access/users/12"),
]


class TestAuth:
    @pytest.mark.parametrize("method, path", PATHS)
    def test_non_admin_forbidden(self, method, path):
        c = _client(USER, default=_uc(), department=_uc(), user=_uc())
        res = c.request(method, path, json={"tool_ids": []})
        assert res.status_code == 403

    @pytest.mark.parametrize("method, path", PATHS)
    def test_unauthenticated_401(self, method, path):
        c = _client(None, default=_uc(), department=_uc(), user=_uc())
        res = c.request(method, path, json={"tool_ids": []})
        assert res.status_code == 401


class TestDefault:
    def test_get(self):
        uc = _uc(get=DefaultToolAccessResponse(tool_ids=[A]))
        res = _client(ADMIN, default=uc).get("/api/v1/admin/tool-access/default")
        assert res.status_code == 200
        assert res.json() == {"tool_ids": [A]}

    def test_put_passes_granted_by(self):
        uc = _uc(replace=DefaultToolAccessResponse(tool_ids=[A]))
        res = _client(ADMIN, default=uc).put(
            "/api/v1/admin/tool-access/default", json={"tool_ids": [A]}
        )
        assert res.status_code == 200
        args, kwargs = uc.replace.call_args
        assert args[0] == [A]
        assert kwargs["granted_by"] == 1

    def test_put_unknown_ids_400(self):
        uc = _uc(replace=UnknownToolIdsError(["internal:nope"]))
        res = _client(ADMIN, default=uc).put(
            "/api/v1/admin/tool-access/default", json={"tool_ids": ["internal:nope"]}
        )
        assert res.status_code == 400
        detail = res.json()["detail"]
        assert detail["code"] == "UNKNOWN_TOOL_IDS"
        assert detail["tool_ids"] == ["internal:nope"]

    def test_put_missing_body_422(self):
        res = _client(ADMIN, default=_uc()).put("/api/v1/admin/tool-access/default")
        assert res.status_code == 422


class TestDepartment:
    _resp = DepartmentToolAccessResponse(
        department_id="d1", department_name="여신부", tool_ids=[A], default_tool_ids=[]
    )

    def test_get(self):
        res = _client(ADMIN, department=_uc(get=self._resp)).get(
            "/api/v1/admin/tool-access/departments/d1"
        )
        assert res.status_code == 200
        assert res.json()["department_name"] == "여신부"

    def test_get_not_found(self):
        res = _client(ADMIN, department=_uc(get=LookupError("없음"))).get(
            "/api/v1/admin/tool-access/departments/x"
        )
        assert res.status_code == 404

    def test_put(self):
        uc = _uc(replace=self._resp)
        res = _client(ADMIN, department=uc).put(
            "/api/v1/admin/tool-access/departments/d1", json={"tool_ids": [A]}
        )
        assert res.status_code == 200
        args, kwargs = uc.replace.call_args
        assert args[:2] == ("d1", [A])
        assert kwargs["granted_by"] == 1

    def test_put_not_found_and_unknown(self):
        c = _client(ADMIN, department=_uc(replace=LookupError("x")))
        assert c.put("/api/v1/admin/tool-access/departments/x", json={"tool_ids": []}).status_code == 404
        c = _client(ADMIN, department=_uc(replace=UnknownToolIdsError(["q"])))
        assert c.put("/api/v1/admin/tool-access/departments/d1", json={"tool_ids": ["q"]}).status_code == 400


class TestUser:
    _resp = UserToolAccessResponse(
        user_id=12, is_admin=False, tool_ids=[A],
        inherited=[InheritedToolAccessResponse(
            tool_id="internal:python_code_executor",
            sources=[ToolGrantSourceResponse(kind="department", department_id="d1", department_name="여신부")],
        )],
    )

    def test_get(self):
        res = _client(ADMIN, user=_uc(get=self._resp)).get("/api/v1/admin/tool-access/users/12")
        assert res.status_code == 200
        body = res.json()
        assert body["inherited"][0]["sources"][0]["kind"] == "department"

    def test_get_invalid_user_id_422(self):
        res = _client(ADMIN, user=_uc(get=self._resp)).get("/api/v1/admin/tool-access/users/abc")
        assert res.status_code == 422

    def test_put_and_errors(self):
        uc = _uc(replace=self._resp)
        res = _client(ADMIN, user=uc).put("/api/v1/admin/tool-access/users/12", json={"tool_ids": [A]})
        assert res.status_code == 200
        args, _ = uc.replace.call_args
        assert args[:2] == (12, [A])
        c = _client(ADMIN, user=_uc(replace=LookupError("x")))
        assert c.put("/api/v1/admin/tool-access/users/99", json={"tool_ids": []}).status_code == 404
