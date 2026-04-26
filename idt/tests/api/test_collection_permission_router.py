from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.collection_router import (
    get_activity_log_service,
    get_collection_use_case,
    router,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.schemas import CollectionInfo
from src.interfaces.dependencies.auth import get_current_user


def _make_user(
    user_id: int = 1,
    role: UserRole = UserRole.USER,
) -> User:
    return User(
        id=user_id,
        email="test@example.com",
        password_hash="hashed",
        role=role,
        status=UserStatus.APPROVED,
    )


@pytest.fixture
def mock_use_case() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_activity_log() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def current_user() -> User:
    return _make_user()


@pytest.fixture
def client(
    mock_use_case: AsyncMock,
    mock_activity_log: AsyncMock,
    current_user: User,
) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_collection_use_case] = lambda: mock_use_case
    app.dependency_overrides[get_activity_log_service] = lambda: mock_activity_log
    app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app)


class TestListCollectionsWithPermission:
    def test_includes_scope_and_owner(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        mock_use_case.list_collections.return_value = [
            CollectionInfo("my-docs", 10, 10, "green"),
        ]
        mock_use_case.get_permissions_map.return_value = {
            "my-docs": ("PERSONAL", 1),
        }
        resp = client.get("/api/v1/collections")
        assert resp.status_code == 200
        item = resp.json()["collections"][0]
        assert item["scope"] == "PERSONAL"
        assert item["owner_id"] == 1

    def test_no_permission_returns_null_scope(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        mock_use_case.list_collections.return_value = [
            CollectionInfo("legacy", 5, 5, "green"),
        ]
        mock_use_case.get_permissions_map.return_value = {}
        resp = client.get("/api/v1/collections")
        assert resp.status_code == 200
        item = resp.json()["collections"][0]
        assert item["scope"] is None
        assert item["owner_id"] is None


class TestCreateCollectionWithScope:
    def test_with_scope_parameter(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        resp = client.post(
            "/api/v1/collections",
            json={
                "name": "team-docs",
                "vector_size": 1536,
                "scope": "DEPARTMENT",
                "department_id": "dept-1",
            },
        )
        assert resp.status_code == 201
        call_kwargs = mock_use_case.create_collection.call_args
        from src.domain.collection.permission_schemas import CollectionScope
        assert call_kwargs.kwargs.get("scope") == CollectionScope.DEPARTMENT
        assert call_kwargs.kwargs.get("department_id") == "dept-1"

    def test_invalid_scope_returns_422(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        resp = client.post(
            "/api/v1/collections",
            json={
                "name": "bad",
                "vector_size": 1536,
                "scope": "INVALID_SCOPE",
            },
        )
        assert resp.status_code == 422


class TestChangeCollectionScope:
    def test_success(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        resp = client.patch(
            "/api/v1/collections/my-docs/permission",
            json={"scope": "PUBLIC"},
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "Collection scope updated successfully"
        mock_use_case.change_scope.assert_awaited_once()

    def test_permission_denied_returns_403(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        mock_use_case.change_scope.side_effect = PermissionError(
            "No permission to change scope"
        )
        resp = client.patch(
            "/api/v1/collections/other-docs/permission",
            json={"scope": "PUBLIC"},
        )
        assert resp.status_code == 403

    def test_not_found_returns_404(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        mock_use_case.change_scope.side_effect = ValueError(
            "Permission not found for collection 'ghost'"
        )
        resp = client.patch(
            "/api/v1/collections/ghost/permission",
            json={"scope": "PUBLIC"},
        )
        assert resp.status_code == 404

    def test_invalid_scope_returns_422(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        resp = client.patch(
            "/api/v1/collections/my-docs/permission",
            json={"scope": "INVALID"},
        )
        assert resp.status_code == 422

    def test_department_required_returns_422(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        mock_use_case.change_scope.side_effect = ValueError(
            "department_id is required for DEPARTMENT scope"
        )
        resp = client.patch(
            "/api/v1/collections/my-docs/permission",
            json={"scope": "DEPARTMENT"},
        )
        assert resp.status_code == 422

    def test_service_not_configured_returns_501(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        mock_use_case.change_scope.side_effect = RuntimeError(
            "Permission service not configured"
        )
        resp = client.patch(
            "/api/v1/collections/my-docs/permission",
            json={"scope": "PUBLIC"},
        )
        assert resp.status_code == 501


class TestDeleteCollectionPermission:
    def test_permission_denied_returns_403(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        mock_use_case.delete_collection.side_effect = PermissionError(
            "No delete access to collection 'other-docs'"
        )
        resp = client.delete("/api/v1/collections/other-docs")
        assert resp.status_code == 403


class TestRenameCollectionPermission:
    def test_permission_denied_returns_403(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        mock_use_case.rename_collection.side_effect = PermissionError(
            "No delete access to collection 'other-docs'"
        )
        resp = client.patch(
            "/api/v1/collections/other-docs",
            json={"new_name": "new-name"},
        )
        assert resp.status_code == 403
