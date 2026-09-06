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


def _make_fake_user():
    from src.domain.auth.entities import User, UserRole, UserStatus
    return User(
        email="user@test.com",
        password_hash="hashed",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=2,
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


class TestListToolCatalogBuiltin:
    def test_list_exposes_is_builtin(self):
        """builtin-tools D4: 목록 응답에 is_builtin 노출."""
        from src.api.routes.tool_catalog_router import get_list_tool_catalog_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            return_value=ToolCatalogListResponse(
                tools=[
                    ToolCatalogItemResponse(
                        tool_id="internal:wiki_read",
                        source="internal",
                        name="에이전트 위키 열람",
                        description="위키 열람",
                        is_builtin=True,
                    )
                ]
            )
        )
        client = _make_client({get_list_tool_catalog_use_case: lambda: mock_uc})
        resp = client.get("/api/v1/tool-catalog")
        assert resp.status_code == 200
        assert resp.json()["tools"][0]["is_builtin"] is True


class TestSetBuiltin:
    def test_patch_builtin_admin_200(self):
        """builtin-tools D3: 관리자 토글 정상 경로."""
        from src.api.routes.tool_catalog_router import get_set_builtin_use_case
        from src.domain.tool_catalog.entity import ToolCatalogEntry
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            return_value=ToolCatalogEntry(
                id="tc-1", tool_id="internal:wiki_read", source="internal",
                name="에이전트 위키 열람", description="d", is_builtin=True,
            )
        )
        client = _make_client({get_set_builtin_use_case: lambda: mock_uc})
        resp = client.patch(
            "/api/v1/tool-catalog/builtin",
            json={"tool_id": "internal:wiki_read", "is_builtin": True},
        )
        assert resp.status_code == 200
        assert resp.json() == {"tool_id": "internal:wiki_read", "is_builtin": True}

    def test_patch_builtin_unknown_tool_404(self):
        from src.api.routes.tool_catalog_router import get_set_builtin_use_case
        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            side_effect=ValueError("Unknown catalog tool_id: 'internal:nope'")
        )
        client = _make_client({get_set_builtin_use_case: lambda: mock_uc})
        resp = client.patch(
            "/api/v1/tool-catalog/builtin",
            json={"tool_id": "internal:nope", "is_builtin": True},
        )
        assert resp.status_code == 404

    def test_patch_builtin_non_admin_403(self):
        from src.api.routes.tool_catalog_router import get_set_builtin_use_case
        from src.interfaces.dependencies.auth import get_current_user
        mock_uc = MagicMock()
        client = _make_client({
            get_set_builtin_use_case: lambda: mock_uc,
            get_current_user: _make_fake_user,
        })
        resp = client.patch(
            "/api/v1/tool-catalog/builtin",
            json={"tool_id": "internal:wiki_read", "is_builtin": True},
        )
        assert resp.status_code == 403
        mock_uc.execute.assert_not_called()


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


class TestUpdateToolMetadata:
    """Design Ref: mcp-tool-category-routing §4.2 (FR-13).

    엔드포인트 형태는 set_builtin과 같은 body 방식이다 — 카탈로그 tool_id
    (mcp:{uuid}:{tool})가 콜론·임의 도구명을 포함해 path 세그먼트로 부적합하다.
    """

    @staticmethod
    def _mock_uc(entry=None):
        from src.domain.tool_catalog.entity import ToolCatalogEntry

        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            return_value=entry or ToolCatalogEntry(
                id="tc-1",
                tool_id="mcp:3f2a1b4c-0000-1111-2222-333344445555:scrape",
                source="mcp", name="scrape", description="d",
                category="collect", max_tool_calls=2,
            )
        )
        return mock_uc

    def test_update_metadata_returns_200(self):
        from src.api.routes.tool_catalog_router import (
            get_update_tool_metadata_use_case,
        )

        mock_uc = self._mock_uc()
        client = _make_client({get_update_tool_metadata_use_case: lambda: mock_uc})

        res = client.patch(
            "/api/v1/tool-catalog/metadata",
            json={
                "tool_id": "mcp:3f2a1b4c-0000-1111-2222-333344445555:scrape",
                "category": "collect",
                "max_tool_calls": 2,
            },
        )

        assert res.status_code == 200
        body = res.json()
        assert body["category"] == "collect"
        assert body["max_tool_calls"] == 2

    def test_omitted_field_is_not_forwarded(self):
        """부분 갱신: body에 없는 필드는 유스케이스에 전달되지 않는다."""
        from src.api.routes.tool_catalog_router import (
            get_update_tool_metadata_use_case,
        )

        mock_uc = self._mock_uc()
        client = _make_client({get_update_tool_metadata_use_case: lambda: mock_uc})

        client.patch(
            "/api/v1/tool-catalog/metadata",
            json={
                "tool_id": "mcp:3f2a1b4c-0000-1111-2222-333344445555:scrape",
                "category": "collect",
            },
        )

        assert "max_tool_calls" not in mock_uc.execute.await_args.kwargs

    def test_explicit_null_is_forwarded(self):
        """명시적 null은 '미분류로 되돌리기' — 생략과 구분해 전달한다."""
        from src.api.routes.tool_catalog_router import (
            get_update_tool_metadata_use_case,
        )

        mock_uc = self._mock_uc()
        client = _make_client({get_update_tool_metadata_use_case: lambda: mock_uc})

        client.patch(
            "/api/v1/tool-catalog/metadata",
            json={
                "tool_id": "mcp:3f2a1b4c-0000-1111-2222-333344445555:scrape",
                "category": None,
            },
        )

        assert mock_uc.execute.await_args.kwargs["category"] is None

    def test_domain_error_returns_400(self):
        """허용값 밖 카테고리 / collect on server-level → 400 (D-04)."""
        from src.api.routes.tool_catalog_router import (
            get_update_tool_metadata_use_case,
        )

        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            side_effect=ValueError("collect category requires a single-tool reference")
        )
        client = _make_client({get_update_tool_metadata_use_case: lambda: mock_uc})

        res = client.patch(
            "/api/v1/tool-catalog/metadata",
            json={"tool_id": "mcp_srv1", "category": "collect"},
        )

        assert res.status_code == 400
        assert "collect" in res.json()["detail"]

    def test_unknown_tool_returns_404(self):
        from src.api.routes.tool_catalog_router import (
            get_update_tool_metadata_use_case,
        )

        mock_uc = MagicMock()
        mock_uc.execute = AsyncMock(
            side_effect=LookupError("Unknown catalog tool_id: 'nope'")
        )
        client = _make_client({get_update_tool_metadata_use_case: lambda: mock_uc})

        res = client.patch(
            "/api/v1/tool-catalog/metadata",
            json={"tool_id": "nope", "category": "collect"},
        )

        assert res.status_code == 404

    def test_non_admin_is_rejected(self):
        from src.api.routes.tool_catalog_router import (
            get_update_tool_metadata_use_case,
            router,
        )
        from src.interfaces.dependencies.auth import get_current_user

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = _make_fake_user
        app.dependency_overrides[get_update_tool_metadata_use_case] = (
            lambda: self._mock_uc()
        )
        client = TestClient(app)

        res = client.patch(
            "/api/v1/tool-catalog/metadata",
            json={"tool_id": "x", "category": "collect"},
        )

        assert res.status_code == 403
