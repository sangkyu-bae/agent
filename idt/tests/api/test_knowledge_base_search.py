"""Tests for KB search endpoints (kb-retrieval-test §3.2)."""
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection_search.search_history_schemas import (
    KbSearchHistoryListResult,
    SearchHistoryEntry,
)
from src.domain.hybrid_search.schemas import HybridSearchResult
from src.domain.knowledge_base.search_schemas import KbSearchResult


def _make_user() -> User:
    return User(
        email="test@example.com",
        password_hash="hash",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=1,
    )


def _make_search_result(document_id: str | None = None) -> KbSearchResult:
    return KbSearchResult(
        query="test query",
        kb_id="kb-1",
        kb_name="테스트 KB",
        collection_name="col-a",
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
                metadata={"document_id": "d1"},
            )
        ],
        total_found=1,
        bm25_weight=0.5,
        vector_weight=0.5,
        request_id="req-1",
        document_id=document_id,
    )


def _make_history_result() -> KbSearchHistoryListResult:
    return KbSearchHistoryListResult(
        kb_id="kb-1",
        histories=[
            SearchHistoryEntry(
                id=1,
                user_id="1",
                collection_name="col-a",
                query="test",
                bm25_weight=0.5,
                vector_weight=0.5,
                top_k=10,
                result_count=5,
                created_at=datetime(2026, 7, 18, 10, 30),
                kb_id="kb-1",
            )
        ],
        total=1,
        limit=20,
        offset=0,
    )


@pytest.fixture
def client():
    from fastapi import FastAPI

    from src.api.routes.knowledge_base_router import (
        get_kb_search_history_use_case,
        get_kb_search_use_case,
        router,
    )
    from src.interfaces.dependencies.auth import get_current_user

    app = FastAPI()
    app.include_router(router)

    mock_search_uc = AsyncMock()
    mock_history_uc = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: _make_user()
    app.dependency_overrides[get_kb_search_use_case] = lambda: mock_search_uc
    app.dependency_overrides[get_kb_search_history_use_case] = (
        lambda: mock_history_uc
    )

    test_client = TestClient(app)
    test_client.mock_search_uc = mock_search_uc
    test_client.mock_history_uc = mock_history_uc
    return test_client


class TestKbSearchEndpoint:
    def test_search_returns_200(self, client):
        client.mock_search_uc.execute = AsyncMock(
            return_value=_make_search_result()
        )

        res = client.post(
            "/api/v1/knowledge-bases/kb-1/search",
            json={"query": "test query"},
        )

        assert res.status_code == 200
        body = res.json()
        assert body["kb_id"] == "kb-1"
        assert body["kb_name"] == "테스트 KB"
        assert body["total_found"] == 1
        assert body["results"][0]["id"] == "chunk-1"

    def test_search_passes_document_id(self, client):
        client.mock_search_uc.execute = AsyncMock(
            return_value=_make_search_result(document_id="d1")
        )

        res = client.post(
            "/api/v1/knowledge-bases/kb-1/search",
            json={"query": "q", "document_id": "d1"},
        )

        assert res.status_code == 200
        assert res.json()["document_id"] == "d1"
        domain_request = client.mock_search_uc.execute.call_args[0][1]
        assert domain_request.document_id == "d1"

    def test_permission_error_maps_403(self, client):
        client.mock_search_uc.execute = AsyncMock(
            side_effect=PermissionError("No read access")
        )

        res = client.post(
            "/api/v1/knowledge-bases/kb-1/search", json={"query": "q"}
        )

        assert res.status_code == 403

    def test_not_found_maps_404(self, client):
        client.mock_search_uc.execute = AsyncMock(
            side_effect=ValueError("Knowledge base 'kb-x' not found")
        )

        res = client.post(
            "/api/v1/knowledge-bases/kb-x/search", json={"query": "q"}
        )

        assert res.status_code == 404

    def test_embedding_resolve_failure_maps_422(self, client):
        client.mock_search_uc.execute = AsyncMock(
            side_effect=ValueError("Cannot determine embedding model")
        )

        res = client.post(
            "/api/v1/knowledge-bases/kb-1/search", json={"query": "q"}
        )

        assert res.status_code == 422

    def test_empty_query_rejected_422(self, client):
        res = client.post(
            "/api/v1/knowledge-bases/kb-1/search", json={"query": ""}
        )

        assert res.status_code == 422


class TestKbSearchHistoryEndpoint:
    def test_history_returns_200(self, client):
        client.mock_history_uc.execute = AsyncMock(
            return_value=_make_history_result()
        )

        res = client.get("/api/v1/knowledge-bases/kb-1/search-history")

        assert res.status_code == 200
        body = res.json()
        assert body["kb_id"] == "kb-1"
        assert body["total"] == 1
        assert body["histories"][0]["query"] == "test"

    def test_history_pagination_params(self, client):
        client.mock_history_uc.execute = AsyncMock(
            return_value=_make_history_result()
        )

        res = client.get(
            "/api/v1/knowledge-bases/kb-1/search-history?limit=5&offset=10"
        )

        assert res.status_code == 200
        kwargs = client.mock_history_uc.execute.call_args.kwargs
        assert kwargs["limit"] == 5
        assert kwargs["offset"] == 10

    def test_history_permission_error_maps_403(self, client):
        client.mock_history_uc.execute = AsyncMock(
            side_effect=PermissionError("No read access")
        )

        res = client.get("/api/v1/knowledge-bases/kb-1/search-history")

        assert res.status_code == 403
