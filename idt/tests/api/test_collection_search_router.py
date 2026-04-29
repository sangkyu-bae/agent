"""Tests for collection_search_router API endpoints."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.application.collection_search.use_case import CollectionNotFoundError
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection_search.schemas import CollectionSearchResponse
from src.domain.collection_search.search_history_schemas import (
    SearchHistoryEntry,
    SearchHistoryListResult,
)
from src.domain.hybrid_search.schemas import HybridSearchResult


def _make_user() -> User:
    return User(
        email="test@example.com",
        password_hash="hash",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=1,
    )


def _make_search_response() -> CollectionSearchResponse:
    return CollectionSearchResponse(
        query="test query",
        collection_name="my-col",
        results=[
            HybridSearchResult(
                id="chunk-1",
                content="some content",
                score=0.025,
                bm25_rank=1,
                bm25_score=10.0,
                vector_rank=2,
                vector_score=0.85,
                source="both",
                metadata={"doc_id": "d1"},
            )
        ],
        total_found=1,
        bm25_weight=0.5,
        vector_weight=0.5,
        request_id="req-1",
    )


def _make_history_response() -> SearchHistoryListResult:
    return SearchHistoryListResult(
        collection_name="my-col",
        histories=[
            SearchHistoryEntry(
                id=1,
                user_id="1",
                collection_name="my-col",
                query="test",
                bm25_weight=0.5,
                vector_weight=0.5,
                top_k=10,
                result_count=5,
                created_at=datetime(2026, 4, 28, 10, 30),
            )
        ],
        total=1,
        limit=20,
        offset=0,
    )


@pytest.fixture
def client():
    from fastapi import FastAPI

    from src.api.routes.collection_search_router import (
        get_collection_search_use_case,
        get_search_history_use_case,
        router,
    )
    from src.interfaces.dependencies.auth import get_current_user

    app = FastAPI()
    app.include_router(router)

    mock_search_uc = AsyncMock()
    mock_history_uc = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: _make_user()
    app.dependency_overrides[get_collection_search_use_case] = lambda: mock_search_uc
    app.dependency_overrides[get_search_history_use_case] = lambda: mock_history_uc

    test_client = TestClient(app)
    test_client.mock_search_uc = mock_search_uc
    test_client.mock_history_uc = mock_history_uc
    return test_client


class TestCollectionSearchEndpoint:
    def test_collection_search_200(self, client):
        client.mock_search_uc.execute = AsyncMock(
            return_value=_make_search_response()
        )

        resp = client.post(
            "/api/v1/collections/my-col/search",
            json={"query": "test query"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["collection_name"] == "my-col"
        assert body["total_found"] == 1
        assert len(body["results"]) == 1

    def test_document_search_200(self, client):
        resp_data = _make_search_response()
        client.mock_search_uc.execute = AsyncMock(return_value=resp_data)

        resp = client.post(
            "/api/v1/collections/my-col/documents/doc-1/search",
            json={"query": "test query"},
        )

        assert resp.status_code == 200

    def test_permission_error_403(self, client):
        client.mock_search_uc.execute = AsyncMock(
            side_effect=PermissionError("No read access")
        )

        resp = client.post(
            "/api/v1/collections/my-col/search",
            json={"query": "test"},
        )

        assert resp.status_code == 403

    def test_collection_not_found_404(self, client):
        client.mock_search_uc.execute = AsyncMock(
            side_effect=CollectionNotFoundError("missing")
        )

        resp = client.post(
            "/api/v1/collections/missing/search",
            json={"query": "test"},
        )

        assert resp.status_code == 404

    def test_invalid_weight_422(self, client):
        resp = client.post(
            "/api/v1/collections/my-col/search",
            json={"query": "test", "bm25_weight": 2.0},
        )

        assert resp.status_code == 422

    def test_empty_query_422(self, client):
        resp = client.post(
            "/api/v1/collections/my-col/search",
            json={"query": ""},
        )

        assert resp.status_code == 422


class TestSearchHistoryEndpoint:
    def test_get_history_200(self, client):
        client.mock_history_uc.execute = AsyncMock(
            return_value=_make_history_response()
        )

        resp = client.get("/api/v1/collections/my-col/search-history")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["histories"]) == 1

    def test_get_history_with_pagination(self, client):
        client.mock_history_uc.execute = AsyncMock(
            return_value=SearchHistoryListResult(
                collection_name="c",
                histories=[],
                total=0,
                limit=5,
                offset=10,
            )
        )

        resp = client.get(
            "/api/v1/collections/c/search-history?limit=5&offset=10"
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["limit"] == 5
        assert body["offset"] == 10
