"""Tests for HybridSearch domain schemas. Domain: mock 금지."""
import pytest


class TestHybridSearchRequest:
    def test_create_with_query_only(self):
        from src.domain.hybrid_search.schemas import HybridSearchRequest
        req = HybridSearchRequest(query="금융 정책 문서")
        assert req.query == "금융 정책 문서"

    def test_default_top_k_is_10(self):
        from src.domain.hybrid_search.schemas import HybridSearchRequest
        req = HybridSearchRequest(query="q")
        assert req.top_k == 10

    def test_default_bm25_top_k_is_20(self):
        from src.domain.hybrid_search.schemas import HybridSearchRequest
        req = HybridSearchRequest(query="q")
        assert req.bm25_top_k == 20

    def test_default_vector_top_k_is_20(self):
        from src.domain.hybrid_search.schemas import HybridSearchRequest
        req = HybridSearchRequest(query="q")
        assert req.vector_top_k == 20

    def test_default_rrf_k_is_60(self):
        from src.domain.hybrid_search.schemas import HybridSearchRequest
        req = HybridSearchRequest(query="q")
        assert req.rrf_k == 60

    def test_custom_params(self):
        from src.domain.hybrid_search.schemas import HybridSearchRequest
        req = HybridSearchRequest(query="q", top_k=5, bm25_top_k=10, vector_top_k=10, rrf_k=30)
        assert req.top_k == 5 and req.rrf_k == 30


class TestHybridSearchResult:
    def test_create_full(self):
        from src.domain.hybrid_search.schemas import HybridSearchResult
        r = HybridSearchResult(
            id="doc-1", content="내용", score=0.025,
            bm25_rank=1, bm25_score=10.5,
            vector_rank=2, vector_score=0.85,
            source="both", metadata={"type": "pdf"},
        )
        assert r.id == "doc-1" and r.source == "both"

    def test_bm25_only_source(self):
        from src.domain.hybrid_search.schemas import HybridSearchResult
        r = HybridSearchResult(
            id="d", content="c", score=0.016,
            bm25_rank=1, bm25_score=5.0,
            vector_rank=None, vector_score=None,
            source="bm25_only", metadata={},
        )
        assert r.source == "bm25_only" and r.vector_rank is None

    def test_vector_only_source(self):
        from src.domain.hybrid_search.schemas import HybridSearchResult
        r = HybridSearchResult(
            id="d", content="c", score=0.016,
            bm25_rank=None, bm25_score=None,
            vector_rank=3, vector_score=0.7,
            source="vector_only", metadata={},
        )
        assert r.source == "vector_only" and r.bm25_rank is None


class TestSearchHit:
    def test_create(self):
        from src.domain.hybrid_search.schemas import SearchHit
        hit = SearchHit(id="doc-1", content="내용", metadata={"k": "v"}, raw_score=7.5)
        assert hit.id == "doc-1" and hit.raw_score == 7.5


class TestHybridSearchResponse:
    def test_create(self):
        from src.domain.hybrid_search.schemas import HybridSearchResponse
        resp = HybridSearchResponse(query="q", results=[], total_found=0, request_id="r-1")
        assert resp.query == "q" and resp.total_found == 0
