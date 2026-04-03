"""MorphIndex domain schema tests — no mocks."""
import pytest

from src.domain.morph_index.schemas import (
    DualIndexedChunk,
    MorphIndexRequest,
    MorphIndexResult,
)


class TestMorphIndexRequest:
    def test_creates_with_required_fields(self):
        req = MorphIndexRequest(
            document_id="doc-1",
            content="금융 정책 문서",
            user_id="user-1",
        )
        assert req.document_id == "doc-1"
        assert req.content == "금융 정책 문서"
        assert req.user_id == "user-1"

    def test_default_values(self):
        req = MorphIndexRequest(
            document_id="doc-1", content="텍스트", user_id="u1"
        )
        assert req.strategy_type == "parent_child"
        assert req.chunk_size == 500
        assert req.chunk_overlap == 50
        assert req.source == ""
        assert req.metadata == {}


class TestDualIndexedChunk:
    def test_creates_with_all_fields(self):
        chunk = DualIndexedChunk(
            chunk_id="cid-1",
            chunk_type="child",
            morph_keywords=["금융", "달리다"],
            content="금융 정책",
            char_start=0,
            char_end=5,
            chunk_index=0,
        )
        assert chunk.chunk_id == "cid-1"
        assert chunk.morph_keywords == ["금융", "달리다"]
        assert chunk.char_start == 0
        assert chunk.char_end == 5


class TestMorphIndexResult:
    def test_creates_correctly(self):
        chunk = DualIndexedChunk(
            chunk_id="cid-1",
            chunk_type="child",
            morph_keywords=["금융"],
            content="금융",
            char_start=0,
            char_end=2,
            chunk_index=0,
        )
        result = MorphIndexResult(
            document_id="doc-1",
            user_id="u1",
            total_chunks=1,
            qdrant_indexed=1,
            es_indexed=1,
            indexed_chunks=[chunk],
            request_id="req-1",
        )
        assert result.total_chunks == 1
        assert result.qdrant_indexed == 1
        assert result.es_indexed == 1
        assert len(result.indexed_chunks) == 1
