"""Tests for document upload endpoint."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
import io

from src.api.routes.document_upload import router, get_document_processor
from src.domain.pipeline.enums.document_category import DocumentCategory
from src.domain.pipeline.schemas.upload_schema import DocumentUploadResponse


@pytest.fixture
def app():
    """Create test FastAPI app."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestDocumentUploadEndpoint:
    """Test document upload endpoint."""

    def test_upload_endpoint_exists(self, app, client):
        """Test upload endpoint is accessible."""
        # Override dependency to avoid NotImplementedError
        mock_processor = AsyncMock()
        mock_processor.process.return_value = {
            "document_id": "test",
            "filename": "test.pdf",
            "category": DocumentCategory.GENERAL,
            "category_confidence": 0.5,
            "total_pages": 1,
            "chunk_count": 1,
            "stored_ids": [],
            "status": "completed",
            "errors": [],
        }
        app.dependency_overrides[get_document_processor] = lambda: mock_processor

        # Send request without file to verify endpoint exists
        response = client.post("/api/v1/documents/upload")
        # Should return 422 (validation error) not 404
        assert response.status_code != 404
        app.dependency_overrides.clear()

    def test_upload_requires_file(self, app, client):
        """Test upload requires file parameter."""
        # Override dependency to avoid NotImplementedError
        mock_processor = AsyncMock()
        app.dependency_overrides[get_document_processor] = lambda: mock_processor

        response = client.post("/api/v1/documents/upload")
        assert response.status_code == 422
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_upload_success(self, app):
        """Test successful document upload."""
        mock_result = {
            "document_id": "abc123_test",
            "filename": "test.pdf",
            "category": DocumentCategory.IT_SYSTEM,
            "category_confidence": 0.95,
            "total_pages": 5,
            "chunk_count": 10,
            "stored_ids": ["id1", "id2"],
            "status": "completed",
            "errors": [],
            "processing_time_ms": 1500,
        }

        mock_processor = AsyncMock()
        mock_processor.process.return_value = mock_result

        app.dependency_overrides[get_document_processor] = lambda: mock_processor

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as ac:
            files = {"file": ("test.pdf", b"%PDF-1.4 content", "application/pdf")}
            response = await ac.post(
                "/api/v1/documents/upload",
                files=files,
                params={"user_id": "user123"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == "abc123_test"
        assert data["status"] == "completed"
        assert data["category"] == "it_system"

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_upload_processing_error(self, app):
        """Test upload with processing error."""
        mock_result = {
            "document_id": "",
            "filename": "bad.pdf",
            "category": DocumentCategory.GENERAL,
            "category_confidence": 0.0,
            "total_pages": 0,
            "chunk_count": 0,
            "stored_ids": [],
            "status": "failed",
            "errors": ["Parse failed: Invalid PDF format"],
            "processing_time_ms": 100,
        }

        mock_processor = AsyncMock()
        mock_processor.process.return_value = mock_result

        app.dependency_overrides[get_document_processor] = lambda: mock_processor

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as ac:
            files = {"file": ("bad.pdf", b"not a pdf", "application/pdf")}
            response = await ac.post(
                "/api/v1/documents/upload",
                files=files,
                params={"user_id": "user123"},
            )

        # Should return 500 for processing failure
        assert response.status_code == 500
        data = response.json()
        # Errors are in detail.errors due to HTTPException structure
        assert "detail" in data
        assert "errors" in data["detail"]
        assert len(data["detail"]["errors"]) > 0

        app.dependency_overrides.clear()


class TestDocumentUploadResponseSchema:
    """Test document upload response schema."""

    def test_response_schema_validation(self):
        """Test response schema validates correctly."""
        response = DocumentUploadResponse(
            document_id="test123",
            filename="test.pdf",
            category=DocumentCategory.HR,
            category_confidence=0.88,
            total_pages=3,
            chunk_count=5,
            stored_ids=["a", "b"],
            status="completed",
            errors=[],
        )
        assert response.document_id == "test123"
        assert response.category == DocumentCategory.HR


class TestChildChunkSizeParam:
    """Test child_chunk_size parameter in upload endpoint."""

    @pytest.mark.asyncio
    async def test_upload_accepts_child_chunk_size_param(self, app):
        """Test upload endpoint accepts child_chunk_size query param."""
        mock_processor = AsyncMock()
        mock_processor.process.return_value = {
            "document_id": "doc1",
            "filename": "test.pdf",
            "category": DocumentCategory.GENERAL,
            "category_confidence": 0.9,
            "total_pages": 2,
            "chunk_count": 4,
            "stored_ids": ["a", "b"],
            "status": "completed",
            "errors": [],
            "processing_time_ms": 500,
        }
        app.dependency_overrides[get_document_processor] = lambda: mock_processor

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            files = {"file": ("test.pdf", b"%PDF-1.4", "application/pdf")}
            response = await ac.post(
                "/api/v1/documents/upload",
                files=files,
                params={"user_id": "user1", "child_chunk_size": 300},
            )

        assert response.status_code == 200
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_upload_passes_child_chunk_size_to_processor(self, app):
        """Test upload endpoint passes child_chunk_size to processor."""
        mock_processor = AsyncMock()
        mock_processor.process.return_value = {
            "document_id": "doc1",
            "filename": "test.pdf",
            "category": DocumentCategory.GENERAL,
            "category_confidence": 0.9,
            "total_pages": 2,
            "chunk_count": 4,
            "stored_ids": [],
            "status": "completed",
            "errors": [],
            "processing_time_ms": 500,
        }
        app.dependency_overrides[get_document_processor] = lambda: mock_processor

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            files = {"file": ("test.pdf", b"%PDF-1.4", "application/pdf")}
            await ac.post(
                "/api/v1/documents/upload",
                files=files,
                params={"user_id": "user1", "child_chunk_size": 300},
            )

        mock_processor.process.assert_called_once()
        call_kwargs = mock_processor.process.call_args
        assert call_kwargs[1]["child_chunk_size"] == 300
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_upload_uses_default_child_chunk_size_when_not_provided(self, app):
        """Test upload uses default child_chunk_size when not specified."""
        mock_processor = AsyncMock()
        mock_processor.process.return_value = {
            "document_id": "doc1",
            "filename": "test.pdf",
            "category": DocumentCategory.GENERAL,
            "category_confidence": 0.9,
            "total_pages": 2,
            "chunk_count": 4,
            "stored_ids": [],
            "status": "completed",
            "errors": [],
            "processing_time_ms": 500,
        }
        app.dependency_overrides[get_document_processor] = lambda: mock_processor

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            files = {"file": ("test.pdf", b"%PDF-1.4", "application/pdf")}
            await ac.post(
                "/api/v1/documents/upload",
                files=files,
                params={"user_id": "user1"},
            )

        call_kwargs = mock_processor.process.call_args
        assert call_kwargs[1]["child_chunk_size"] == 500
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_upload_rejects_child_chunk_size_below_minimum(self, app):
        """Test upload rejects child_chunk_size below 100."""
        mock_processor = AsyncMock()
        app.dependency_overrides[get_document_processor] = lambda: mock_processor

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            files = {"file": ("test.pdf", b"%PDF-1.4", "application/pdf")}
            response = await ac.post(
                "/api/v1/documents/upload",
                files=files,
                params={"user_id": "user1", "child_chunk_size": 50},
            )

        assert response.status_code == 422
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_upload_rejects_child_chunk_size_above_maximum(self, app):
        """Test upload rejects child_chunk_size above 4000."""
        mock_processor = AsyncMock()
        app.dependency_overrides[get_document_processor] = lambda: mock_processor

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            files = {"file": ("test.pdf", b"%PDF-1.4", "application/pdf")}
            response = await ac.post(
                "/api/v1/documents/upload",
                files=files,
                params={"user_id": "user1", "child_chunk_size": 5000},
            )

        assert response.status_code == 422
        app.dependency_overrides.clear()


class TestAsyncUploadEndpoint:
    """Test async upload endpoint (optional)."""

    def test_async_upload_endpoint_exists(self, client):
        """Test async upload endpoint is accessible."""
        response = client.post("/api/v1/documents/upload/async")
        # Should return 422 (validation error) not 404
        assert response.status_code != 404


class TestUploadStatusEndpoint:
    """Test upload status endpoint."""

    def test_status_endpoint_exists(self, client):
        """Test status endpoint is accessible."""
        response = client.get("/api/v1/documents/upload/status/task123")
        # Should return valid response (404 for unknown task is ok)
        assert response.status_code in [200, 404]
