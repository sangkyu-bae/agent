"""Tests for retrieval API router.

TDD: tests written before implementation.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from src.domain.retrieval.schemas import RetrievalResult, RetrievedDocument


def _make_result(query: str = "금리 인상", n_docs: int = 2) -> RetrievalResult:
    docs = [
        RetrievedDocument(
            id=f"doc_{i}",
            content=f"content {i}",
            score=0.9 - i * 0.05,
            metadata={"chunk_type": "child"},
            parent_content=f"parent {i}",
        )
        for i in range(n_docs)
    ]
    return RetrievalResult(
        query=query,
        rewritten_query=None,
        documents=docs,
        total_found=n_docs,
        request_id="req_test",
    )


@pytest.fixture
def client():
    from fastapi import FastAPI
    from src.api.routes.retrieval_router import router, get_retrieval_use_case

    mock_uc = AsyncMock()
    mock_uc.execute = AsyncMock(return_value=_make_result())

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_retrieval_use_case] = lambda: mock_uc

    return TestClient(app)


class TestRetrievalRouter:
    def test_search_returns_200(self, client):
        """Valid request returns 200."""
        response = client.post(
            "/api/v1/retrieval/search",
            json={"query": "금리 인상", "user_id": "user_1"},
        )
        assert response.status_code == 200

    def test_search_response_schema(self, client):
        """Response contains expected fields."""
        response = client.post(
            "/api/v1/retrieval/search",
            json={"query": "금리 인상", "user_id": "user_1"},
        )
        data = response.json()
        assert "query" in data
        assert "documents" in data
        assert "total_found" in data
        assert "request_id" in data
        assert isinstance(data["documents"], list)

    def test_search_document_fields(self, client):
        """Each document contains id, content, score, metadata."""
        response = client.post(
            "/api/v1/retrieval/search",
            json={"query": "금리 인상", "user_id": "user_1"},
        )
        doc = response.json()["documents"][0]
        assert "id" in doc
        assert "content" in doc
        assert "score" in doc
        assert "metadata" in doc

    def test_search_missing_query_returns_422(self, client):
        """Missing query field returns 422."""
        response = client.post(
            "/api/v1/retrieval/search",
            json={"user_id": "user_1"},
        )
        assert response.status_code == 422

    def test_search_missing_user_id_returns_422(self, client):
        """Missing user_id field returns 422."""
        response = client.post(
            "/api/v1/retrieval/search",
            json={"query": "금리 인상"},
        )
        assert response.status_code == 422

    def test_search_passes_options_to_use_case(self, client):
        """Request options are forwarded to use case."""
        response = client.post(
            "/api/v1/retrieval/search",
            json={
                "query": "금리 인상",
                "user_id": "user_1",
                "top_k": 5,
                "use_compression": False,
                "use_parent_context": False,
            },
        )
        assert response.status_code == 200
