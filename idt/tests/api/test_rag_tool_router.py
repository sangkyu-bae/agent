"""RAG Tool Router 단위 테스트."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.api.routes.rag_tool_router import (
    router, get_qdrant_client, get_collection_aliases,
    get_collection_permission_service,
)
from src.domain.auth.entities import User, UserRole
from src.domain.collection.permission_schemas import CollectionPermission, CollectionScope
from src.interfaces.dependencies.auth import get_current_user


def _make_app():
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router)
    return app


def _mock_collection(name: str, vectors_count: int = 100):
    c = MagicMock()
    c.name = name
    c.vectors_count = vectors_count
    return c


def _mock_record(payload: dict):
    r = MagicMock()
    r.payload = payload
    return r


@pytest.fixture
def mock_qdrant():
    client = MagicMock()
    collections_result = MagicMock()
    collections_result.collections = [
        _mock_collection("documents", 500),
        _mock_collection("finance_docs", 200),
    ]
    client.get_collections = AsyncMock(return_value=collections_result)
    client.scroll = AsyncMock(return_value=(
        [
            _mock_record({"content": "text", "department": "finance", "category": "policy"}),
            _mock_record({"content": "text2", "department": "tech", "category": "manual"}),
        ],
        None,
    ))
    return client


@pytest.fixture
def mock_user():
    return User(
        id=1, email="test@test.com", password_hash="hash",
        role=UserRole.USER,
    )


@pytest.fixture
def mock_perm_service():
    service = MagicMock()
    service.get_accessible_collection_names = AsyncMock(
        return_value={"documents", "finance_docs"}
    )

    async def _find_perm(name, req_id):
        perms = {
            "documents": CollectionPermission(
                collection_name="documents", owner_id=1, scope=CollectionScope.PUBLIC,
            ),
            "finance_docs": CollectionPermission(
                collection_name="finance_docs", owner_id=1, scope=CollectionScope.DEPARTMENT,
            ),
        }
        return perms.get(name)

    service.find_permission = AsyncMock(side_effect=_find_perm)
    return service


@pytest.fixture
def app(mock_qdrant, mock_user, mock_perm_service):
    app = _make_app()
    app.dependency_overrides[get_qdrant_client] = lambda: mock_qdrant
    app.dependency_overrides[get_collection_aliases] = lambda: {
        "documents": "전체 문서",
        "finance_docs": "금융 문서",
    }
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_collection_permission_service] = lambda: mock_perm_service
    return app


class TestListCollections:
    @pytest.mark.asyncio
    async def test_returns_collection_list(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/rag-tools/collections")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["collections"]) == 2
        names = [c["name"] for c in data["collections"]]
        assert "documents" in names
        assert "finance_docs" in names

    @pytest.mark.asyncio
    async def test_applies_display_name_alias(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/rag-tools/collections")

        data = resp.json()
        finance = next(c for c in data["collections"] if c["name"] == "finance_docs")
        assert finance["display_name"] == "금융 문서"

    @pytest.mark.asyncio
    async def test_includes_vectors_count(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/rag-tools/collections")

        data = resp.json()
        docs = next(c for c in data["collections"] if c["name"] == "documents")
        assert docs["vectors_count"] == 500


class TestListMetadataKeys:
    @pytest.mark.asyncio
    async def test_returns_metadata_keys(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/rag-tools/metadata-keys")

        assert resp.status_code == 200
        data = resp.json()
        key_names = [k["key"] for k in data["keys"]]
        assert "department" in key_names
        assert "category" in key_names
        assert "content" not in key_names

    @pytest.mark.asyncio
    async def test_returns_sample_values(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/rag-tools/metadata-keys")

        data = resp.json()
        dept = next(k for k in data["keys"] if k["key"] == "department")
        assert "finance" in dept["sample_values"]
        assert "tech" in dept["sample_values"]

    @pytest.mark.asyncio
    async def test_passes_collection_name_param(self, app, mock_qdrant):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.get(
                "/api/v1/rag-tools/metadata-keys?collection_name=finance_docs"
            )

        mock_qdrant.scroll.assert_called_once()
        call_kwargs = mock_qdrant.scroll.call_args
        assert call_kwargs.kwargs["collection_name"] == "finance_docs"


class TestCollectionScope:
    @pytest.mark.asyncio
    async def test_collections_include_scope(self, app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/rag-tools/collections")

        data = resp.json()
        docs = next(c for c in data["collections"] if c["name"] == "documents")
        assert docs["scope"] == "PUBLIC"
        finance = next(c for c in data["collections"] if c["name"] == "finance_docs")
        assert finance["scope"] == "DEPARTMENT"

    @pytest.mark.asyncio
    async def test_inaccessible_collections_filtered(
        self, mock_qdrant, mock_user, mock_perm_service
    ):
        extra_col = _mock_collection("secret_docs", 50)
        mock_qdrant.get_collections.return_value.collections.append(extra_col)
        mock_perm_service.get_accessible_collection_names = AsyncMock(
            return_value={"documents"}
        )

        app = _make_app()
        app.dependency_overrides[get_qdrant_client] = lambda: mock_qdrant
        app.dependency_overrides[get_collection_aliases] = lambda: {}
        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[get_collection_permission_service] = lambda: mock_perm_service

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/v1/rag-tools/collections")

        names = [c["name"] for c in resp.json()["collections"]]
        assert "documents" in names
        assert "secret_docs" not in names
        assert "finance_docs" not in names
