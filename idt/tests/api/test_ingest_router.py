"""Tests for ingest router — POST /api/v1/ingest/pdf."""
import io
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.domain.ingest.schemas import IngestResult


def _make_use_case_mock(parser_used: str = "pymupdf") -> MagicMock:
    uc = MagicMock()
    uc.ingest = AsyncMock(
        return_value=IngestResult(
            document_id="abc_test",
            filename="test.pdf",
            user_id="user_1",
            total_pages=2,
            chunk_count=4,
            parser_used=parser_used,
            chunking_strategy="full_token",
            stored_ids=["id-1", "id-2", "id-3", "id-4"],
            request_id="req_001",
        )
    )
    return uc


@pytest.fixture
def client():
    from src.api.routes.ingest_router import router, get_ingest_use_case

    app = FastAPI()
    app.include_router(router)

    mock_uc = _make_use_case_mock()
    app.dependency_overrides[get_ingest_use_case] = lambda: mock_uc

    return TestClient(app), mock_uc


def _pdf_file(content: bytes = b"%PDF-1.4 fake") -> tuple:
    return ("file", ("test.pdf", io.BytesIO(content), "application/pdf"))


# ───────────────────────────────────────────────
# Success cases
# ───────────────────────────────────────────────

def test_upload_pdf_returns_200_with_result(client):
    tc, _ = client
    resp = tc.post(
        "/api/v1/ingest/pdf",
        params={"user_id": "user_1"},
        files=[_pdf_file()],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == "abc_test"
    assert body["chunk_count"] == 4
    assert body["parser_used"] == "pymupdf"


def test_upload_pdf_default_parser_is_pymupdf(client):
    tc, mock_uc = client
    tc.post(
        "/api/v1/ingest/pdf",
        params={"user_id": "u1"},
        files=[_pdf_file()],
    )
    call_kwargs = mock_uc.ingest.call_args
    request = call_kwargs.args[0]
    assert request.parser_type == "pymupdf"


def test_upload_pdf_with_llamaparser(client):
    tc, mock_uc = client
    mock_uc.ingest.return_value = IngestResult(
        document_id="llama_doc",
        filename="test.pdf",
        user_id="u1",
        total_pages=1,
        chunk_count=2,
        parser_used="llamaparser",
        chunking_strategy="full_token",
        stored_ids=["a", "b"],
        request_id="r",
    )
    resp = tc.post(
        "/api/v1/ingest/pdf",
        params={"user_id": "u1", "parser_type": "llamaparser"},
        files=[_pdf_file()],
    )
    assert resp.status_code == 200
    assert resp.json()["parser_used"] == "llamaparser"

    call_request = mock_uc.ingest.call_args.args[0]
    assert call_request.parser_type == "llamaparser"


def test_upload_pdf_chunking_strategy_passed_to_use_case(client):
    tc, mock_uc = client
    tc.post(
        "/api/v1/ingest/pdf",
        params={"user_id": "u1", "chunking_strategy": "parent_child", "chunk_size": 800},
        files=[_pdf_file()],
    )
    req = mock_uc.ingest.call_args.args[0]
    assert req.chunking_strategy == "parent_child"
    assert req.chunk_size == 800


# ───────────────────────────────────────────────
# Validation cases
# ───────────────────────────────────────────────

def test_upload_pdf_missing_user_id_returns_422(client):
    tc, _ = client
    resp = tc.post(
        "/api/v1/ingest/pdf",
        files=[_pdf_file()],
    )
    assert resp.status_code == 422


def test_upload_pdf_missing_file_returns_422(client):
    tc, _ = client
    resp = tc.post(
        "/api/v1/ingest/pdf",
        params={"user_id": "u1"},
    )
    assert resp.status_code == 422
