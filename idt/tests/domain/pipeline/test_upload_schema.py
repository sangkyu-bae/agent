"""Tests for upload schema."""
import pytest
from pydantic import ValidationError

from src.domain.pipeline.schemas.upload_schema import DocumentUploadResponse
from src.domain.pipeline.enums.document_category import DocumentCategory


class TestDocumentUploadResponse:
    """Test DocumentUploadResponse schema."""

    def test_valid_upload_response(self):
        """Test creating valid DocumentUploadResponse."""
        response = DocumentUploadResponse(
            document_id="abc123_test_doc",
            filename="test_doc.pdf",
            category=DocumentCategory.IT_SYSTEM,
            category_confidence=0.95,
            total_pages=10,
            chunk_count=25,
            stored_ids=["chunk1", "chunk2", "chunk3"],
            status="completed",
            errors=[],
        )
        assert response.document_id == "abc123_test_doc"
        assert response.filename == "test_doc.pdf"
        assert response.category == DocumentCategory.IT_SYSTEM
        assert response.category_confidence == 0.95
        assert response.total_pages == 10
        assert response.chunk_count == 25
        assert response.stored_ids == ["chunk1", "chunk2", "chunk3"]
        assert response.status == "completed"
        assert response.errors == []

    def test_response_with_errors(self):
        """Test response with error messages."""
        response = DocumentUploadResponse(
            document_id="abc123_failed",
            filename="failed.pdf",
            category=DocumentCategory.GENERAL,
            category_confidence=0.0,
            total_pages=0,
            chunk_count=0,
            stored_ids=[],
            status="failed",
            errors=["Parse error: Invalid PDF", "Connection timeout"],
        )
        assert response.status == "failed"
        assert len(response.errors) == 2
        assert "Parse error: Invalid PDF" in response.errors

    def test_all_categories_valid(self):
        """Test all document categories are valid for response."""
        for category in DocumentCategory:
            response = DocumentUploadResponse(
                document_id="test",
                filename="test.pdf",
                category=category,
                category_confidence=0.5,
                total_pages=1,
                chunk_count=1,
                stored_ids=["id1"],
                status="completed",
                errors=[],
            )
            assert response.category == category


class TestDocumentUploadResponseSerialization:
    """Test DocumentUploadResponse serialization."""

    def test_model_dump_returns_dict(self):
        """Test model_dump returns dictionary."""
        response = DocumentUploadResponse(
            document_id="doc123",
            filename="document.pdf",
            category=DocumentCategory.HR,
            category_confidence=0.8,
            total_pages=5,
            chunk_count=12,
            stored_ids=["a", "b", "c"],
            status="completed",
            errors=[],
        )
        data = response.model_dump()
        assert isinstance(data, dict)
        assert data["document_id"] == "doc123"
        assert data["category"] == DocumentCategory.HR
        assert data["chunk_count"] == 12

    def test_model_dump_json(self):
        """Test model can be serialized to JSON."""
        response = DocumentUploadResponse(
            document_id="doc456",
            filename="report.pdf",
            category=DocumentCategory.ACCOUNTING_LEGAL,
            category_confidence=0.92,
            total_pages=20,
            chunk_count=50,
            stored_ids=["x", "y"],
            status="completed",
            errors=[],
        )
        json_str = response.model_dump_json()
        assert isinstance(json_str, str)
        assert "doc456" in json_str
        assert "accounting_legal" in json_str

    def test_empty_stored_ids_valid(self):
        """Test empty stored_ids list is valid."""
        response = DocumentUploadResponse(
            document_id="empty",
            filename="empty.pdf",
            category=DocumentCategory.GENERAL,
            category_confidence=0.0,
            total_pages=0,
            chunk_count=0,
            stored_ids=[],
            status="pending",
            errors=[],
        )
        assert response.stored_ids == []
