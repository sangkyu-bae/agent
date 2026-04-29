"""Tests for search history domain schemas. Domain: mock 금지."""
from datetime import datetime


class TestSearchHistoryEntry:
    def test_create(self):
        from src.domain.collection_search.search_history_schemas import (
            SearchHistoryEntry,
        )

        entry = SearchHistoryEntry(
            id=1,
            user_id="u1",
            collection_name="c",
            query="q",
            bm25_weight=0.5,
            vector_weight=0.5,
            top_k=10,
            result_count=5,
            created_at=datetime(2026, 4, 28),
        )
        assert entry.id == 1
        assert entry.document_id is None

    def test_with_document_id(self):
        from src.domain.collection_search.search_history_schemas import (
            SearchHistoryEntry,
        )

        entry = SearchHistoryEntry(
            id=2,
            user_id="u1",
            collection_name="c",
            query="q",
            bm25_weight=0.8,
            vector_weight=0.2,
            top_k=10,
            result_count=3,
            created_at=datetime(2026, 4, 28),
            document_id="doc-123",
        )
        assert entry.document_id == "doc-123"


class TestSearchHistoryListResult:
    def test_create(self):
        from src.domain.collection_search.search_history_schemas import (
            SearchHistoryListResult,
        )

        result = SearchHistoryListResult(
            collection_name="c",
            histories=[],
            total=0,
            limit=20,
            offset=0,
        )
        assert result.total == 0
        assert result.limit == 20
