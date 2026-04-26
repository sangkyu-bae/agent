from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.routes.collection_router import (
    get_activity_log_service,
    get_collection_use_case,
    router,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.schemas import (
    ActionType,
    ActivityLogEntry,
    CollectionDetail,
    CollectionInfo,
)
from src.interfaces.dependencies.auth import get_current_user


@pytest.fixture
def mock_use_case() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_activity_log() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def current_user() -> User:
    return User(
        id=1,
        email="test@example.com",
        password_hash="hashed",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
    )


@pytest.fixture
def client(
    mock_use_case: AsyncMock,
    mock_activity_log: AsyncMock,
    current_user: User,
) -> TestClient:
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_collection_use_case] = lambda: mock_use_case
    app.dependency_overrides[get_activity_log_service] = lambda: mock_activity_log
    app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app)


class TestListCollections:
    def test_returns_200(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        mock_use_case.list_collections.return_value = [
            CollectionInfo("docs", 10, 10, "green")
        ]
        mock_use_case.get_permissions_map.return_value = {}
        resp = client.get("/api/v1/collections")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["collections"][0]["name"] == "docs"


class TestGetCollection:
    def test_returns_200(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        mock_use_case.get_collection.return_value = CollectionDetail(
            "test", 5, 5, "green", 1536, "Cosine"
        )
        resp = client.get("/api/v1/collections/test")
        assert resp.status_code == 200
        assert resp.json()["config"]["vector_size"] == 1536

    def test_returns_404(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        mock_use_case.get_collection.side_effect = ValueError("not found")
        resp = client.get("/api/v1/collections/nonexistent")
        assert resp.status_code == 404


class TestCreateCollection:
    def test_returns_201(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        resp = client.post(
            "/api/v1/collections",
            json={"name": "new-col", "vector_size": 1536, "distance": "Cosine"},
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "new-col"

    def test_duplicate_returns_409(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        mock_use_case.create_collection.side_effect = ValueError("already exists")
        resp = client.post(
            "/api/v1/collections",
            json={"name": "dup", "vector_size": 1536},
        )
        assert resp.status_code == 409

    def test_invalid_name_returns_422(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        mock_use_case.create_collection.side_effect = ValueError(
            "Invalid collection name"
        )
        resp = client.post(
            "/api/v1/collections",
            json={"name": "bad name!", "vector_size": 1536},
        )
        assert resp.status_code == 422


class TestRenameCollection:
    def test_returns_200(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        resp = client.patch(
            "/api/v1/collections/old-name",
            json={"new_name": "new-name"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["old_name"] == "old-name"
        assert data["new_name"] == "new-name"

    def test_not_found_returns_404(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        mock_use_case.rename_collection.side_effect = ValueError("not found")
        resp = client.patch(
            "/api/v1/collections/ghost",
            json={"new_name": "new-name"},
        )
        assert resp.status_code == 404


class TestDeleteCollection:
    def test_returns_200(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        resp = client.delete("/api/v1/collections/my-col")
        assert resp.status_code == 200

    def test_protected_returns_403(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        mock_use_case.delete_collection.side_effect = ValueError(
            "Cannot delete protected collection"
        )
        resp = client.delete("/api/v1/collections/documents")
        assert resp.status_code == 403

    def test_not_found_returns_404(
        self, client: TestClient, mock_use_case: AsyncMock
    ) -> None:
        mock_use_case.delete_collection.side_effect = ValueError("not found")
        resp = client.delete("/api/v1/collections/ghost")
        assert resp.status_code == 404


class TestActivityLog:
    def test_global_activity_log(
        self, client: TestClient, mock_activity_log: AsyncMock
    ) -> None:
        now = datetime(2026, 4, 21, 10, 0, 0)
        entry = ActivityLogEntry(
            id=1,
            collection_name="docs",
            action=ActionType.SEARCH,
            user_id="u1",
            detail={"query": "test"},
            created_at=now,
        )
        mock_activity_log.get_logs.return_value = ([entry], 1)
        resp = client.get("/api/v1/collections/activity-log")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["logs"][0]["action"] == "SEARCH"

    def test_collection_activity_log(
        self, client: TestClient, mock_activity_log: AsyncMock
    ) -> None:
        mock_activity_log.get_collection_logs.return_value = ([], 0)
        resp = client.get("/api/v1/collections/docs/activity-log")
        assert resp.status_code == 200
        assert resp.json()["logs"] == []
        assert resp.json()["total"] == 0


class TestRoutingOrder:
    def test_activity_log_not_captured_by_name(
        self, client: TestClient, mock_activity_log: AsyncMock, mock_use_case: AsyncMock
    ) -> None:
        """activity-log 경로가 {name} 파라미터로 캡처되지 않는지 확인."""
        mock_activity_log.get_logs.return_value = ([], 0)
        resp = client.get("/api/v1/collections/activity-log")
        assert resp.status_code == 200
        mock_use_case.get_collection.assert_not_called()
