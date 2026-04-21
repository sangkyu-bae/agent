"""Department Router 단위 테스트 — TestClient + Mock UseCase."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.department.schemas import (
    DepartmentListResponse,
    DepartmentResponse,
)


def _make_fake_admin():
    from src.domain.auth.entities import User, UserRole, UserStatus
    return User(
        email="admin@test.com",
        password_hash="hashed",
        role=UserRole.ADMIN,
        status=UserStatus.APPROVED,
        id=1,
    )


def _make_client(overrides: dict) -> TestClient:
    from src.api.routes.department_router import router
    from src.interfaces.dependencies.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _make_fake_admin
    for dep, override in overrides.items():
        app.dependency_overrides[dep] = override
    return TestClient(app)


def _dept_response(dept_id: str = "dept-1") -> DepartmentResponse:
    return DepartmentResponse(
        id=dept_id,
        name="개발팀",
        description="개발 부서",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )


class TestListDepartments:
    def test_list_returns_200(self):
        from src.api.routes.department_router import get_list_departments_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            return_value=DepartmentListResponse(departments=[_dept_response()])
        )
        client = _make_client({get_list_departments_use_case: lambda: mock_uc})
        resp = client.get("/api/v1/departments")
        assert resp.status_code == 200
        assert len(resp.json()["departments"]) == 1


class TestCreateDepartment:
    def test_create_returns_201(self):
        from src.api.routes.department_router import get_create_department_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=_dept_response())
        client = _make_client({get_create_department_use_case: lambda: mock_uc})
        resp = client.post(
            "/api/v1/departments",
            json={"name": "개발팀", "description": "개발 부서"},
        )
        assert resp.status_code == 201

    def test_create_duplicate_returns_409(self):
        from src.api.routes.department_router import get_create_department_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            side_effect=ValueError("이미 존재하는 부서 이름입니다: 개발팀")
        )
        client = _make_client({get_create_department_use_case: lambda: mock_uc})
        resp = client.post(
            "/api/v1/departments", json={"name": "개발팀"}
        )
        assert resp.status_code == 409


class TestUpdateDepartment:
    def test_update_returns_200(self):
        from src.api.routes.department_router import get_update_department_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=_dept_response())
        client = _make_client({get_update_department_use_case: lambda: mock_uc})
        resp = client.patch(
            "/api/v1/departments/dept-1", json={"name": "수정된 이름"}
        )
        assert resp.status_code == 200

    def test_update_not_found_returns_404(self):
        from src.api.routes.department_router import get_update_department_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            side_effect=ValueError("부서를 찾을 수 없습니다: dept-99")
        )
        client = _make_client({get_update_department_use_case: lambda: mock_uc})
        resp = client.patch(
            "/api/v1/departments/dept-99", json={"name": "새이름"}
        )
        assert resp.status_code == 404


class TestDeleteDepartment:
    def test_delete_returns_204(self):
        from src.api.routes.department_router import get_delete_department_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=None)
        client = _make_client({get_delete_department_use_case: lambda: mock_uc})
        resp = client.delete("/api/v1/departments/dept-1")
        assert resp.status_code == 204

    def test_delete_not_found_returns_404(self):
        from src.api.routes.department_router import get_delete_department_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            side_effect=ValueError("부서를 찾을 수 없습니다: dept-99")
        )
        client = _make_client({get_delete_department_use_case: lambda: mock_uc})
        resp = client.delete("/api/v1/departments/dept-99")
        assert resp.status_code == 404


class TestAssignUserDepartment:
    def test_assign_returns_204(self):
        from src.api.routes.department_router import get_assign_user_department_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=None)
        client = _make_client({get_assign_user_department_use_case: lambda: mock_uc})
        resp = client.post(
            "/api/v1/users/1/departments",
            json={"department_id": "dept-1", "is_primary": False},
        )
        assert resp.status_code == 204


class TestRemoveUserDepartment:
    def test_remove_returns_204(self):
        from src.api.routes.department_router import get_remove_user_department_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=None)
        client = _make_client({get_remove_user_department_use_case: lambda: mock_uc})
        resp = client.delete("/api/v1/users/1/departments/dept-1")
        assert resp.status_code == 204
