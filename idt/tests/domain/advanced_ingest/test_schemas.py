import pytest

from src.domain.advanced_ingest.schemas import (
    AdvancedIngestRequest,
    AdvancedIngestResult,
)


class TestAdvancedIngestRequest:
    """AdvancedIngestRequest 도메인 스키마 검증."""

    def _make_valid_kwargs(self, **overrides) -> dict:
        base = {
            "filename": "report.pdf",
            "user_id": "user-001",
            "request_id": "req-abc-123",
            "file_bytes": b"%PDF-1.4 fake content",
            "collection_name": "documents",
            "chunking_strategy": "parent_child",
            "chunk_size": 500,
            "chunk_overlap": 50,
            "enable_layout_analysis": True,
            "enable_table_flattening": True,
            "sample_pages": 3,
        }
        base.update(overrides)
        return base

    def test_valid_construction(self):
        req = AdvancedIngestRequest(**self._make_valid_kwargs())
        assert req.filename == "report.pdf"
        assert req.user_id == "user-001"
        assert req.request_id == "req-abc-123"
        assert req.file_bytes == b"%PDF-1.4 fake content"
        assert req.collection_name == "documents"
        assert req.chunking_strategy == "parent_child"
        assert req.chunk_size == 500
        assert req.chunk_overlap == 50
        assert req.enable_layout_analysis is True
        assert req.enable_table_flattening is True
        assert req.sample_pages == 3

    def test_defaults(self):
        req = AdvancedIngestRequest(
            filename="test.pdf",
            user_id="u1",
            request_id="r1",
            file_bytes=b"data",
        )
        assert req.collection_name == "documents"
        assert req.chunking_strategy == "parent_child"
        assert req.chunk_size == 500
        assert req.chunk_overlap == 50
        assert req.enable_layout_analysis is True
        assert req.enable_table_flattening is True
        assert req.sample_pages == 3

    def test_filename_empty_rejected(self):
        with pytest.raises(ValueError, match="filename cannot be empty"):
            AdvancedIngestRequest(**self._make_valid_kwargs(filename=""))

    def test_filename_whitespace_only_rejected(self):
        with pytest.raises(ValueError, match="filename cannot be empty"):
            AdvancedIngestRequest(**self._make_valid_kwargs(filename="   "))

    def test_user_id_empty_rejected(self):
        with pytest.raises(ValueError, match="user_id cannot be empty"):
            AdvancedIngestRequest(**self._make_valid_kwargs(user_id=""))

    def test_user_id_whitespace_only_rejected(self):
        with pytest.raises(ValueError, match="user_id cannot be empty"):
            AdvancedIngestRequest(**self._make_valid_kwargs(user_id="  "))

    def test_chunk_size_below_minimum(self):
        with pytest.raises(Exception):
            AdvancedIngestRequest(**self._make_valid_kwargs(chunk_size=50))

    def test_chunk_size_above_maximum(self):
        with pytest.raises(Exception):
            AdvancedIngestRequest(**self._make_valid_kwargs(chunk_size=9000))

    def test_chunk_size_at_boundaries(self):
        req_min = AdvancedIngestRequest(**self._make_valid_kwargs(chunk_size=100))
        assert req_min.chunk_size == 100
        req_max = AdvancedIngestRequest(**self._make_valid_kwargs(chunk_size=8000))
        assert req_max.chunk_size == 8000

    def test_chunk_overlap_below_minimum(self):
        with pytest.raises(Exception):
            AdvancedIngestRequest(**self._make_valid_kwargs(chunk_overlap=-1))

    def test_chunk_overlap_above_maximum(self):
        with pytest.raises(Exception):
            AdvancedIngestRequest(**self._make_valid_kwargs(chunk_overlap=501))

    def test_sample_pages_below_minimum(self):
        with pytest.raises(Exception):
            AdvancedIngestRequest(**self._make_valid_kwargs(sample_pages=0))

    def test_sample_pages_above_maximum(self):
        with pytest.raises(Exception):
            AdvancedIngestRequest(**self._make_valid_kwargs(sample_pages=11))

    def test_arbitrary_types_allowed(self):
        req = AdvancedIngestRequest(**self._make_valid_kwargs())
        assert isinstance(req.file_bytes, bytes)


class TestAdvancedIngestResult:
    """AdvancedIngestResult 도메인 스키마 검증."""

    def test_valid_construction(self):
        result = AdvancedIngestResult(
            document_id="doc-abc-123",
            filename="report.pdf",
            user_id="user-001",
            total_pages=10,
            document_type="table_heavy",
            analysis_confidence=0.92,
            routed_parser="pymupdf4llm",
            layout_quality_score=0.85,
            layout_applied=True,
            table_count=5,
            table_flattened=True,
            chunk_count=42,
            chunking_strategy="parent_child",
            qdrant_indexed=42,
            es_indexed=42,
            processing_time_ms=3500,
            step_timings={"analyze": 200, "route": 5, "parse": 1200},
            collection_name="documents",
            request_id="req-xyz-789",
            errors=[],
        )
        assert result.document_id == "doc-abc-123"
        assert result.total_pages == 10
        assert result.document_type == "table_heavy"
        assert result.analysis_confidence == 0.92
        assert result.routed_parser == "pymupdf4llm"
        assert result.layout_quality_score == 0.85
        assert result.layout_applied is True
        assert result.table_count == 5
        assert result.chunk_count == 42
        assert result.qdrant_indexed == 42
        assert result.es_indexed == 42
        assert result.processing_time_ms == 3500
        assert result.step_timings["analyze"] == 200

    def test_defaults(self):
        result = AdvancedIngestResult(
            document_id="doc-1",
            filename="test.pdf",
            user_id="u1",
            total_pages=1,
        )
        assert result.document_type is None
        assert result.analysis_confidence == 0.0
        assert result.routed_parser == ""
        assert result.layout_quality_score is None
        assert result.layout_applied is False
        assert result.table_count == 0
        assert result.table_flattened is False
        assert result.chunk_count == 0
        assert result.chunking_strategy == ""
        assert result.qdrant_indexed == 0
        assert result.es_indexed == 0
        assert result.processing_time_ms == 0
        assert result.step_timings == {}
        assert result.collection_name == ""
        assert result.request_id == ""
        assert result.errors == []

    def test_partial_result_with_errors(self):
        result = AdvancedIngestResult(
            document_id="doc-2",
            filename="broken.pdf",
            user_id="u1",
            total_pages=5,
            document_type="text_heavy",
            routed_parser="pymupdf",
            chunk_count=0,
            qdrant_indexed=0,
            es_indexed=0,
            errors=["Chunking failed: Invalid token count"],
        )
        assert result.errors == ["Chunking failed: Invalid token count"]
        assert result.chunk_count == 0

    def test_step_timings_default_factory(self):
        r1 = AdvancedIngestResult(
            document_id="d1", filename="a.pdf", user_id="u", total_pages=1
        )
        r2 = AdvancedIngestResult(
            document_id="d2", filename="b.pdf", user_id="u", total_pages=1
        )
        r1.step_timings["analyze"] = 100
        assert "analyze" not in r2.step_timings

    def test_errors_default_factory(self):
        r1 = AdvancedIngestResult(
            document_id="d1", filename="a.pdf", user_id="u", total_pages=1
        )
        r2 = AdvancedIngestResult(
            document_id="d2", filename="b.pdf", user_id="u", total_pages=1
        )
        r1.errors.append("err")
        assert r2.errors == []
