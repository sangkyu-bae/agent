"""Tool Catalog Router 단위 테스트 — TestClient + Mock UseCase."""
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.application.tool_catalog.schemas import (
    ToolCatalogItemResponse,
    ToolCatalogListResponse,
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
    from src.api.routes.tool_catalog_router import router
    from src.interfaces.dependencies.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = _make_fake_admin
    for dep, override in overrides.items():
        app.dependency_overrides[dep] = override
    return TestClient(app)


class TestListToolCatalog:
    def test_list_returns_200(self):
        from src.api.routes.tool_catalog_router import get_list_tool_catalog_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            return_value=ToolCatalogListResponse(
                tools=[
                    ToolCatalogItemResponse(
                        tool_id="internal:tavily_search",
                        source="internal",
                        name="Tavily 웹 검색",
                        description="웹 검색 도구",
                    )
                ]
            )
        )
        client = _make_client({get_list_tool_catalog_use_case: lambda: mock_uc})
        resp = client.get("/api/v1/tool-catalog")
        assert resp.status_code == 200
        assert len(resp.json()["tools"]) == 1

    def test_list_empty_returns_200(self):
        from src.api.routes.tool_catalog_router import get_list_tool_catalog_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            return_value=ToolCatalogListResponse(tools=[])
        )
        client = _make_client({get_list_tool_catalog_use_case: lambda: mock_uc})
        resp = client.get("/api/v1/tool-catalog")
        assert resp.status_code == 200
        assert resp.json()["tools"] == []


class TestSyncMcpTools:
    def test_sync_returns_200_with_count(self):
        from src.api.routes.tool_catalog_router import get_sync_mcp_tools_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=5)
        client = _make_client({get_sync_mcp_tools_use_case: lambda: mock_uc})
        resp = client.post("/api/v1/tool-catalog/sync", json={})
        assert resp.status_code == 200
        assert resp.json()["synced_count"] == 5

    def test_sync_specific_server(self):
        from src.api.routes.tool_catalog_router import get_sync_mcp_tools_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(return_value=3)
        client = _make_client({get_sync_mcp_tools_use_case: lambda: mock_uc})
        resp = client.post(
            "/api/v1/tool-catalog/sync",
            json={"mcp_server_id": "server-1"},
        )
        assert resp.status_code == 200
        assert resp.json()["synced_count"] == 3
