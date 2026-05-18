from src.infrastructure.pipeline.state.advanced_pipeline_state import (
    AdvancedPipelineState,
    create_advanced_initial_state,
)


class TestAdvancedPipelineState:
    """AdvancedPipelineState TypedDict 구조 검증."""

    def test_is_typed_dict(self):
        assert hasattr(AdvancedPipelineState, "__annotations__")
        annotations = AdvancedPipelineState.__annotations__
        assert "file_bytes" in annotations
        assert "document_type" in annotations
        assert "routed_parser_type" in annotations
        assert "parsed_documents" in annotations
        assert "chunked_documents" in annotations
        assert "qdrant_stored_ids" in annotations
        assert "es_stored_count" in annotations
        assert "status" in annotations

    def test_has_all_expected_fields(self):
        expected_fields = {
            "file_path", "file_bytes", "filename", "user_id", "request_id",
            "collection_name", "chunking_strategy", "chunk_size", "chunk_overlap",
            "enable_layout_analysis", "enable_table_flattening", "sample_pages",
            "document_type", "analysis_confidence", "analysis_metrics",
            "routed_parser_type", "routing_reason", "is_fallback",
            "parsed_documents", "total_pages", "document_id",
            "layout_quality_score", "layout_applied",
            "table_count", "table_flattened", "preprocessed_documents",
            "chunked_documents", "chunk_count",
            "morph_applied", "morph_keywords_per_chunk",
            "qdrant_stored_ids", "qdrant_stored_count", "es_stored_count",
            "es_index_name",
            "processing_time_ms", "step_timings", "errors", "status",
        }
        annotations = set(AdvancedPipelineState.__annotations__.keys())
        assert expected_fields == annotations


class TestCreateAdvancedInitialState:
    """create_advanced_initial_state() 팩토리 함수 검증."""

    def test_returns_dict(self):
        state = create_advanced_initial_state(
            file_bytes=b"pdf-data",
            filename="test.pdf",
            user_id="user-1",
            request_id="req-1",
        )
        assert isinstance(state, dict)

    def test_input_fields_set(self):
        state = create_advanced_initial_state(
            file_bytes=b"pdf",
            filename="doc.pdf",
            user_id="u1",
            request_id="r1",
            collection_name="my_col",
        )
        assert state["file_bytes"] == b"pdf"
        assert state["filename"] == "doc.pdf"
        assert state["user_id"] == "u1"
        assert state["request_id"] == "r1"
        assert state["collection_name"] == "my_col"

    def test_defaults(self):
        state = create_advanced_initial_state(
            file_bytes=b"x",
            filename="a.pdf",
            user_id="u",
            request_id="r",
        )
        assert state["collection_name"] == "documents"
        assert state["chunking_strategy"] == "parent_child"
        assert state["chunk_size"] == 500
        assert state["chunk_overlap"] == 50
        assert state["enable_layout_analysis"] is True
        assert state["enable_table_flattening"] is True
        assert state["sample_pages"] == 3

    def test_initial_processing_fields_empty(self):
        state = create_advanced_initial_state(
            file_bytes=b"x",
            filename="a.pdf",
            user_id="u",
            request_id="r",
        )
        assert state["document_type"] is None
        assert state["analysis_confidence"] == 0.0
        assert state["analysis_metrics"] == {}
        assert state["routed_parser_type"] == ""
        assert state["is_fallback"] is False
        assert state["parsed_documents"] == []
        assert state["total_pages"] == 0
        assert state["document_id"] == ""
        assert state["layout_quality_score"] is None
        assert state["layout_applied"] is False
        assert state["table_count"] == 0
        assert state["table_flattened"] is False
        assert state["preprocessed_documents"] == []
        assert state["chunked_documents"] == []
        assert state["chunk_count"] == 0
        assert state["morph_applied"] is False
        assert state["morph_keywords_per_chunk"] == []
        assert state["qdrant_stored_ids"] == []
        assert state["qdrant_stored_count"] == 0
        assert state["es_stored_count"] == 0
        assert state["es_index_name"] == ""
        assert state["processing_time_ms"] == 0
        assert state["step_timings"] == {}
        assert state["errors"] == []
        assert state["status"] == "pending"

    def test_custom_config(self):
        state = create_advanced_initial_state(
            file_bytes=b"x",
            filename="a.pdf",
            user_id="u",
            request_id="r",
            chunking_strategy="semantic",
            chunk_size=1000,
            chunk_overlap=100,
            enable_layout_analysis=False,
            enable_table_flattening=False,
            sample_pages=5,
        )
        assert state["chunking_strategy"] == "semantic"
        assert state["chunk_size"] == 1000
        assert state["chunk_overlap"] == 100
        assert state["enable_layout_analysis"] is False
        assert state["enable_table_flattening"] is False
        assert state["sample_pages"] == 5

    def test_independent_instances(self):
        s1 = create_advanced_initial_state(
            file_bytes=b"a", filename="a.pdf", user_id="u", request_id="r1"
        )
        s2 = create_advanced_initial_state(
            file_bytes=b"b", filename="b.pdf", user_id="u", request_id="r2"
        )
        s1["errors"].append("err")
        s1["step_timings"]["x"] = 1
        assert s2["errors"] == []
        assert s2["step_timings"] == {}
