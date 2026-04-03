"""API 테스트: MCPRegistryRouter (5 엔드포인트)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.application.mcp_registry.schemas import (
    ListMCPServersResponse,
    MCPServerResponse,
)
from src.api.routes.mcp_registry_router import (
    router,
    get_register_use_case,
    get_list_use_case,
    get_update_use_case,
    get_delete_use_case,
)
from fastapi import FastAPI


def _make_response(id="uuid-1", name="My Tool"):
    return MCPServerResponse(
        id=id,
        user_id="u1",
        name=name,
        description="A tool",
        endpoint="https://mcp.example.com/sse",
        transport="sse",
        input_schema=None,
        is_active=True,
        tool_id=f"mcp_{id}",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def mock_register_uc():
    uc = MagicMock()
    uc.execute = AsyncMock(return_value=_make_response())
    return uc


@pytest.fixture
def mock_list_uc():
    uc = MagicMock()
    uc.execute_all = AsyncMock(
        return_value=ListMCPServersResponse(items=[_make_response()], total=1)
    )
    uc.execute_by_user = AsyncMock(
        return_value=ListMCPServersResponse(items=[_make_response()], total=1)
    )
    uc.execute_by_id = AsyncMock(return_value=_make_response())
    return uc


@pytest.fixture
def mock_update_uc():
    uc = MagicMock()
    uc.execute = AsyncMock(return_value=_make_response(name="Updated"))
    return uc


@pytest.fixture
def mock_delete_uc():
    uc = MagicMock()
    uc.execute = AsyncMock(return_value=True)
    return uc


@pytest.fixture
def client(app, mock_register_uc, mock_list_uc, mock_update_uc, mock_delete_uc):
    app.dependency_overrides[get_register_use_case] = lambda: mock_register_uc
    app.dependency_overrides[get_list_use_case] = lambda: mock_list_uc
    app.dependency_overrides[get_update_use_case] = lambda: mock_update_uc
    app.dependency_overrides[get_delete_use_case] = lambda: mock_delete_uc
    return TestClient(app)


class TestPostMCPRegistry:

    def test_register_returns_201(self, client):
        response = client.post("/api/v1/mcp-registry", json={
            "user_id": "u1",
            "name": "My Tool",
            "description": "Does something",
            "endpoint": "https://mcp.example.com/sse",
        })
        assert response.status_code == 201
        assert response.json()["tool_id"] == "mcp_uuid-1"

    def test_register_returns_422_on_value_error(self, app, mock_list_uc, mock_update_uc, mock_delete_uc):
        fail_uc = MagicMock()
        fail_uc.execute = AsyncMock(side_effect=ValueError("Invalid endpoint URL"))
        app.dependency_overrides[get_register_use_case] = lambda: fail_uc
        c = TestClient(app)
        response = c.post("/api/v1/mcp-registry", json={
            "user_id": "u1", "name": "T", "description": "D",
            "endpoint": "not-a-url",
        })
        assert response.status_code == 422


class TestGetMCPRegistry:

    def test_list_returns_200(self, client):
        response = client.get("/api/v1/mcp-registry")
        assert response.status_code == 200
        assert response.json()["total"] == 1

    def test_list_by_user_id_returns_200(self, client):
        response = client.get("/api/v1/mcp-registry?user_id=u1")
        assert response.status_code == 200

    def test_get_by_id_returns_200(self, client):
        response = client.get("/api/v1/mcp-registry/uuid-1")
        assert response.status_code == 200
        assert response.json()["id"] == "uuid-1"

    def test_get_by_id_returns_404_when_not_found(self, app, mock_register_uc, mock_update_uc, mock_delete_uc):
        notfound_uc = MagicMock()
        notfound_uc.execute_by_id = AsyncMock(return_value=None)
        app.dependency_overrides[get_list_use_case] = lambda: notfound_uc
        c = TestClient(app)
        response = c.get("/api/v1/mcp-registry/missing")
        assert response.status_code == 404


class TestPutMCPRegistry:

    def test_update_returns_200(self, client):
        response = client.put("/api/v1/mcp-registry/uuid-1", json={"name": "Updated"})
        assert response.status_code == 200
        assert response.json()["name"] == "Updated"


class TestDeleteMCPRegistry:

    def test_delete_returns_204(self, client):
        response = client.delete("/api/v1/mcp-registry/uuid-1")
        assert response.status_code == 204

    def test_delete_returns_404_when_not_found(self, app, mock_register_uc, mock_list_uc, mock_update_uc):
        notfound_uc = MagicMock()
        notfound_uc.execute = AsyncMock(return_value=False)
        app.dependency_overrides[get_delete_use_case] = lambda: notfound_uc
        c = TestClient(app)
        response = c.delete("/api/v1/mcp-registry/missing")
        assert response.status_code == 404
