"""admin_user_router 사용자 생성/목록 테스트 — TestClient + Mock UseCase.

admin-user-registration Design §9.1.
"""
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.auth.admin_create_user_use_case import AdminCreateUserResult
from src.application.auth.list_users_use_case import UserListItem, UserListResult


def _make_user(role="admin"):
    from src.domain.auth.entities import User, UserRole, UserStatus
    return User(
        email="admin@test.com", password_hash="hashed",
        role=UserRole(role), status=UserStatus.APPROVED, id=1,
    )


def _make_client(overrides: dict, current_role: str = "admin") -> TestClient:
    from src.api.routes.admin_user_router import router
    from src.interfaces.dependencies.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _make_user(current_role)
    for dep, override in overrides.items():
        app.dependency_overrides[dep] = override
    return TestClient(app)


def _create_result():
    return AdminCreateUserResult(
        user_id=10, email="new@example.com", role="user", status="approved",
        display_name="배상규", position="대리", employee_no="E1",
        joined_at=None, department_id="d1",
    )


class TestCreateUser:
    def test_create_returns_201(self):
        from src.api.routes.admin_user_router import get_admin_create_user_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=_create_result())
        client = _make_client({get_admin_create_user_use_case: lambda: mock_uc})

        resp = client.post(
            "/api/v1/admin/users",
            json={
                "email": "new@example.com", "password": "secure1234",
                "display_name": "배상규", "position": "대리",
                "role": "user", "department_id": "d1",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] == 10
        assert body["status"] == "approved"

    def test_duplicate_email_returns_409(self):
        from src.api.routes.admin_user_router import get_admin_create_user_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            side_effect=ValueError("Email already registered: x")
        )
        client = _make_client({get_admin_create_user_use_case: lambda: mock_uc})
        resp = client.post(
            "/api/v1/admin/users",
            json={"email": "x@y.com", "password": "secure1234", "display_name": "x"},
        )
        assert resp.status_code == 409

    def test_invalid_role_returns_422_by_schema(self):
        from src.api.routes.admin_user_router import get_admin_create_user_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=_create_result())
        client = _make_client({get_admin_create_user_use_case: lambda: mock_uc})
        resp = client.post(
            "/api/v1/admin/users",
            json={"email": "x@y.com", "password": "secure1234",
                  "display_name": "x", "role": "superuser"},
        )
        assert resp.status_code == 422

    def test_short_password_returns_422_by_schema(self):
        from src.api.routes.admin_user_router import get_admin_create_user_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=_create_result())
        client = _make_client({get_admin_create_user_use_case: lambda: mock_uc})
        resp = client.post(
            "/api/v1/admin/users",
            json={"email": "x@y.com", "password": "short", "display_name": "x"},
        )
        assert resp.status_code == 422

    def test_non_admin_returns_403(self):
        from src.api.routes.admin_user_router import get_admin_create_user_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=_create_result())
        client = _make_client(
            {get_admin_create_user_use_case: lambda: mock_uc},
            current_role="user",
        )
        resp = client.post(
            "/api/v1/admin/users",
            json={"email": "x@y.com", "password": "secure1234", "display_name": "x"},
        )
        assert resp.status_code == 403


class TestListUsers:
    def test_list_returns_200(self):
        from src.api.routes.admin_user_router import get_list_users_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=UserListResult(
            items=[UserListItem(
                id=1, email="a@b.com", role="user", status="approved",
                display_name="홍길동", position="사원",
                department_names=["여신팀"], created_at=None,
            )],
            total=1,
        ))
        client = _make_client({get_list_users_use_case: lambda: mock_uc})
        resp = client.get("/api/v1/admin/users?status=approved&q=a&limit=10&offset=0")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["department_names"] == ["여신팀"]

    def test_invalid_status_returns_422(self):
        from src.api.routes.admin_user_router import get_list_users_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=UserListResult(items=[], total=0))
        client = _make_client({get_list_users_use_case: lambda: mock_uc})
        resp = client.get("/api/v1/admin/users?status=bogus")
        assert resp.status_code == 422

    def test_non_admin_returns_403(self):
        from src.api.routes.admin_user_router import get_list_users_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=UserListResult(items=[], total=0))
        client = _make_client(
            {get_list_users_use_case: lambda: mock_uc}, current_role="user"
        )
        resp = client.get("/api/v1/admin/users")
        assert resp.status_code == 403
