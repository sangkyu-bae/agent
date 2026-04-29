"""Tests for collection_search domain schemas. Domain: mock 금지."""
import pytest


class TestCollectionSearchRequest:
    def test_create_minimal(self):
        from src.domain.collection_search.schemas import CollectionSearchRequest

        req = CollectionSearchRequest(collection_name="test", query="hello")
        assert req.collection_name == "test"
        assert req.query == "hello"

    def test_defaults(self):
        from src.domain.collection_search.schemas import CollectionSearchRequest

        req = CollectionSearchRequest(collection_name="c", query="q")
        assert req.top_k == 10
        assert req.bm25_weight == 0.5
        assert req.vector_weight == 0.5
        assert req.document_id is None

    def test_empty_collection_name_raises(self):
        from src.domain.collection_search.schemas import CollectionSearchRequest

        with pytest.raises(ValueError, match="collection_name"):
            CollectionSearchRequest(collection_name="", query="q")

    def test_whitespace_collection_name_raises(self):
        from src.domain.collection_search.schemas import CollectionSearchRequest

        with pytest.raises(ValueError, match="collection_name"):
            CollectionSearchRequest(collection_name="   ", query="q")

    def test_empty_query_raises(self):
        from src.domain.collection_search.schemas import CollectionSearchRequest

        with pytest.raises(ValueError, match="query"):
            CollectionSearchRequest(collection_name="c", query="")

    def test_negative_bm25_weight_raises(self):
        from src.domain.collection_search.schemas import CollectionSearchRequest

        with pytest.raises(ValueError, match="bm25_weight"):
            CollectionSearchRequest(
                collection_name="c", query="q", bm25_weight=-0.1
            )

    def test_vector_weight_exceeds_1_raises(self):
        from src.domain.collection_search.schemas import CollectionSearchRequest

        with pytest.raises(ValueError, match="vector_weight"):
            CollectionSearchRequest(
                collection_name="c", query="q", vector_weight=1.5
            )

    def test_document_id_optional(self):
        from src.domain.collection_search.schemas import CollectionSearchRequest

        req = CollectionSearchRequest(
            collection_name="c", query="q", document_id="doc-123"
        )
        assert req.document_id == "doc-123"


class TestCollectionSearchResponse:
    def test_create(self):
        from src.domain.collection_search.schemas import CollectionSearchResponse

        resp = CollectionSearchResponse(
            query="q",
            collection_name="c",
            results=[],
            total_found=0,
            bm25_weight=0.5,
            vector_weight=0.5,
            request_id="r-1",
        )
        assert resp.total_found == 0
        assert resp.document_id is None
