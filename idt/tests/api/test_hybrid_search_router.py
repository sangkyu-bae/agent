"""Tests for hybrid search API router."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI


def make_mock_use_case(results=None):
    from src.domain.hybrid_search.schemas import HybridSearchResponse, HybridSearchResult
    uc = MagicMock()
    uc.execute = AsyncMock(
        return_value=HybridSearchResponse(
            query="test",
            results=results or [
                HybridSearchResult(
                    id="doc-1",
                    content="테스트 내용",
                    score=0.025,
                    bm25_rank=1,
                    bm25_score=8.5,
                    vector_rank=2,
                    vector_score=0.85,
                    source="both",
                    metadata={"type": "pdf"},
                )
            ],
            total_found=1,
            request_id="req-123",
        )
    )
    return uc


@pytest.fixture
def client():
    from src.api.routes.hybrid_search_router import router, get_hybrid_search_use_case

    app = FastAPI()
    app.include_router(router)

    mock_uc = make_mock_use_case()
    app.dependency_overrides[get_hybrid_search_use_case] = lambda: mock_uc

    return TestClient(app)


class TestHybridSearchRouterPost:
    def test_search_returns_200(self, client):
        resp = client.post("/api/v1/hybrid-search/search", json={"query": "금융 정책"})
        assert resp.status_code == 200

    def test_search_response_contains_results(self, client):
        resp = client.post("/api/v1/hybrid-search/search", json={"query": "금융 정책"})
        body = resp.json()
        assert "results" in body
        assert len(body["results"]) == 1

    def test_search_response_contains_query(self, client):
        resp = client.post("/api/v1/hybrid-search/search", json={"query": "금융 정책"})
        body = resp.json()
        assert body["query"] == "test"

    def test_search_result_contains_source_field(self, client):
        resp = client.post("/api/v1/hybrid-search/search", json={"query": "q"})
        result = resp.json()["results"][0]
        assert result["source"] == "both"

    def test_search_result_contains_scores(self, client):
        resp = client.post("/api/v1/hybrid-search/search", json={"query": "q"})
        result = resp.json()["results"][0]
        assert "score" in result
        assert "bm25_score" in result
        assert "vector_score" in result

    def test_missing_query_returns_422(self, client):
        resp = client.post("/api/v1/hybrid-search/search", json={})
        assert resp.status_code == 422

    def test_custom_top_k_accepted(self, client):
        resp = client.post(
            "/api/v1/hybrid-search/search",
            json={"query": "q", "top_k": 5, "bm25_top_k": 15, "vector_top_k": 15},
        )
        assert resp.status_code == 200

    def test_top_k_out_of_range_returns_422(self, client):
        resp = client.post(
            "/api/v1/hybrid-search/search", json={"query": "q", "top_k": 0}
        )
        assert resp.status_code == 422
