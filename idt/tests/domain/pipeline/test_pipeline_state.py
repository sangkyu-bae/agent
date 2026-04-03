"""Tests for PipelineState TypedDict."""
import pytest
from typing import get_type_hints

from src.domain.pipeline.state.pipeline_state import PipelineState
from src.domain.pipeline.enums.document_category import DocumentCategory


class TestPipelineStateStructure:
    """Test PipelineState TypedDict structure."""

    def test_has_file_path_field(self):
        """Test PipelineState has file_path field."""
        hints = get_type_hints(PipelineState)
        assert "file_path" in hints
        assert hints["file_path"] == str

    def test_has_file_bytes_field(self):
        """Test PipelineState has optional file_bytes field."""
        hints = get_type_hints(PipelineState)
        assert "file_bytes" in hints

    def test_has_filename_field(self):
        """Test PipelineState has filename field."""
        hints = get_type_hints(PipelineState)
        assert "filename" in hints
        assert hints["filename"] == str

    def test_has_user_id_field(self):
        """Test PipelineState has user_id field."""
        hints = get_type_hints(PipelineState)
        assert "user_id" in hints
        assert hints["user_id"] == str

    def test_has_parsed_documents_field(self):
        """Test PipelineState has parsed_documents field."""
        hints = get_type_hints(PipelineState)
        assert "parsed_documents" in hints

    def test_has_total_pages_field(self):
        """Test PipelineState has total_pages field."""
        hints = get_type_hints(PipelineState)
        assert "total_pages" in hints
        assert hints["total_pages"] == int

    def test_has_document_id_field(self):
        """Test PipelineState has document_id field."""
        hints = get_type_hints(PipelineState)
        assert "document_id" in hints
        assert hints["document_id"] == str

    def test_has_category_field(self):
        """Test PipelineState has category field."""
        hints = get_type_hints(PipelineState)
        assert "category" in hints

    def test_has_category_confidence_field(self):
        """Test PipelineState has category_confidence field."""
        hints = get_type_hints(PipelineState)
        assert "category_confidence" in hints
        assert hints["category_confidence"] == float

    def test_has_classification_reasoning_field(self):
        """Test PipelineState has classification_reasoning field."""
        hints = get_type_hints(PipelineState)
        assert "classification_reasoning" in hints
        assert hints["classification_reasoning"] == str

    def test_has_sample_pages_field(self):
        """Test PipelineState has sample_pages field."""
        hints = get_type_hints(PipelineState)
        assert "sample_pages" in hints

    def test_has_chunked_documents_field(self):
        """Test PipelineState has chunked_documents field."""
        hints = get_type_hints(PipelineState)
        assert "chunked_documents" in hints

    def test_has_chunk_count_field(self):
        """Test PipelineState has chunk_count field."""
        hints = get_type_hints(PipelineState)
        assert "chunk_count" in hints
        assert hints["chunk_count"] == int

    def test_has_chunking_config_used_field(self):
        """Test PipelineState has chunking_config_used field."""
        hints = get_type_hints(PipelineState)
        assert "chunking_config_used" in hints
        assert hints["chunking_config_used"] == dict

    def test_has_stored_ids_field(self):
        """Test PipelineState has stored_ids field."""
        hints = get_type_hints(PipelineState)
        assert "stored_ids" in hints

    def test_has_collection_name_field(self):
        """Test PipelineState has collection_name field."""
        hints = get_type_hints(PipelineState)
        assert "collection_name" in hints
        assert hints["collection_name"] == str

    def test_has_processing_time_ms_field(self):
        """Test PipelineState has processing_time_ms field."""
        hints = get_type_hints(PipelineState)
        assert "processing_time_ms" in hints
        assert hints["processing_time_ms"] == int

    def test_has_errors_field(self):
        """Test PipelineState has errors field."""
        hints = get_type_hints(PipelineState)
        assert "errors" in hints

    def test_has_status_field(self):
        """Test PipelineState has status field."""
        hints = get_type_hints(PipelineState)
        assert "status" in hints
        assert hints["status"] == str


class TestPipelineStateUsage:
    """Test PipelineState can be used correctly."""

    def test_can_create_initial_state(self):
        """Test creating initial PipelineState."""
        state: PipelineState = {
            "file_path": "/path/to/file.pdf",
            "file_bytes": None,
            "filename": "file.pdf",
            "user_id": "user123",
            "parsed_documents": [],
            "total_pages": 0,
            "document_id": "",
            "category": None,
            "category_confidence": 0.0,
            "classification_reasoning": "",
            "sample_pages": [],
            "chunked_documents": [],
            "chunk_count": 0,
            "chunking_config_used": {},
            "stored_ids": [],
            "collection_name": "",
            "processing_time_ms": 0,
            "errors": [],
            "status": "pending",
        }
        assert state["file_path"] == "/path/to/file.pdf"
        assert state["status"] == "pending"

    def test_can_update_state_after_parsing(self):
        """Test updating state after parsing."""
        state: PipelineState = {
            "file_path": "/path/to/file.pdf",
            "file_bytes": None,
            "filename": "file.pdf",
            "user_id": "user123",
            "parsed_documents": [],
            "total_pages": 0,
            "document_id": "",
            "category": None,
            "category_confidence": 0.0,
            "classification_reasoning": "",
            "sample_pages": [],
            "chunked_documents": [],
            "chunk_count": 0,
            "chunking_config_used": {},
            "stored_ids": [],
            "collection_name": "",
            "processing_time_ms": 0,
            "errors": [],
            "status": "pending",
        }
        # Update after parsing
        state["status"] = "parsing"
        state["total_pages"] = 10
        state["document_id"] = "doc123"

        assert state["status"] == "parsing"
        assert state["total_pages"] == 10

    def test_can_set_category(self):
        """Test setting category in state."""
        state: PipelineState = {
            "file_path": "",
            "file_bytes": None,
            "filename": "",
            "user_id": "",
            "parsed_documents": [],
            "total_pages": 0,
            "document_id": "",
            "category": DocumentCategory.IT_SYSTEM,
            "category_confidence": 0.95,
            "classification_reasoning": "Technical document",
            "sample_pages": [],
            "chunked_documents": [],
            "chunk_count": 0,
            "chunking_config_used": {},
            "stored_ids": [],
            "collection_name": "",
            "processing_time_ms": 0,
            "errors": [],
            "status": "classifying",
        }
        assert state["category"] == DocumentCategory.IT_SYSTEM
        assert state["category_confidence"] == 0.95
