"""Tests for ExcelUploadResponse schema."""
import pytest

from src.domain.pipeline.schemas.excel_upload_schema import ExcelUploadResponse


class TestExcelUploadResponse:
    def test_create_with_required_fields(self):
        response = ExcelUploadResponse(
            document_id="doc-123",
            filename="data.xlsx",
            sheet_count=2,
            chunk_count=10,
            stored_ids=["id1", "id2"],
            status="completed",
            errors=[],
        )
        assert response.document_id == "doc-123"
        assert response.filename == "data.xlsx"
        assert response.sheet_count == 2
        assert response.chunk_count == 10
        assert response.stored_ids == ["id1", "id2"]
        assert response.status == "completed"
        assert response.errors == []

    def test_errors_defaults_to_empty_list(self):
        response = ExcelUploadResponse(
            document_id="doc-123",
            filename="data.xlsx",
            sheet_count=1,
            chunk_count=5,
            stored_ids=[],
            status="completed",
        )
        assert response.errors == []

    def test_failed_status_with_errors(self):
        response = ExcelUploadResponse(
            document_id="",
            filename="bad.xlsx",
            sheet_count=0,
            chunk_count=0,
            stored_ids=[],
            status="failed",
            errors=["Invalid Excel format"],
        )
        assert response.status == "failed"
        assert len(response.errors) == 1
        assert "Invalid Excel format" in response.errors[0]

    def test_serializes_to_dict(self):
        response = ExcelUploadResponse(
            document_id="doc-abc",
            filename="report.xlsx",
            sheet_count=3,
            chunk_count=15,
            stored_ids=["a", "b", "c"],
            status="completed",
            errors=[],
        )
        data = response.model_dump()
        assert data["document_id"] == "doc-abc"
        assert data["sheet_count"] == 3
        assert data["chunk_count"] == 15
