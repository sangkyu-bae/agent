"""Tests for doc-chunk router — POST /api/v1/doc-chunk/upload."""
import io
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.domain.doc_chunk.schemas import DocChunkItem, DocChunkResult


def _make_use_case_mock(total_chunks: int = 3) -> MagicMock:
    chunks = [
        DocChunkItem(
            chunk_id=f"chunk_{i}",
            content=f"Chunk content {i}",
            chunk_type="full",
            chunk_index=i,
            metadata={"filename": "test.txt"},
        )
        for i in range(total_chunks)
    ]
    uc = MagicMock()
    uc.execute = AsyncMock(
        return_value=DocChunkResult(
            filename="test.txt",
            user_id="user_001",
            strategy_used="full_token",
            total_chunks=total_chunks,
            chunks=chunks,
            request_id="req_001",
        )
    )
    return uc


@pytest.fixture
def client():
    from src.api.routes.doc_chunk_router import router, get_doc_chunk_use_case

    app = FastAPI()
    app.include_router(router)

    mock_uc = _make_use_case_mock()
    app.dependency_overrides[get_doc_chunk_use_case] = lambda: mock_uc
    return TestClient(app), mock_uc


def _txt_file(content: bytes = b"Hello world test content.") -> tuple:
    return ("file", ("test.txt", io.BytesIO(content), "text/plain"))


def _pdf_file(content: bytes = b"%PDF-1.4 fake") -> tuple:
    return ("file", ("report.pdf", io.BytesIO(content), "application/pdf"))


# ──────────────────────────────────────────────────────
# 성공 케이스
# ──────────────────────────────────────────────────────

def test_upload_txt_returns_200(client):
    tc, _ = client
    resp = tc.post(
        "/api/v1/doc-chunk/upload",
        params={"user_id": "user_001"},
        files=[_txt_file()],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_chunks"] == 3
    assert data["filename"] == "test.txt"
    assert data["strategy_used"] == "full_token"
    assert len(data["chunks"]) == 3


def test_upload_pdf_returns_200(client):
    tc, _ = client
    resp = tc.post(
        "/api/v1/doc-chunk/upload",
        params={"user_id": "user_001"},
        files=[_pdf_file()],
    )
    assert resp.status_code == 200


def test_upload_with_strategy_param(client):
    tc, mock_uc = client
    tc.post(
        "/api/v1/doc-chunk/upload",
        params={"user_id": "user_001", "strategy_type": "parent_child"},
        files=[_txt_file()],
    )
    call_args = mock_uc.execute.call_args
    assert call_args[0][0].strategy_type == "parent_child"


def test_upload_with_chunk_size_param(client):
    tc, mock_uc = client
    tc.post(
        "/api/v1/doc-chunk/upload",
        params={"user_id": "user_001", "chunk_size": 300},
        files=[_txt_file()],
    )
    call_args = mock_uc.execute.call_args
    assert call_args[0][0].chunk_size == 300


def test_upload_with_chunk_overlap_param(client):
    tc, mock_uc = client
    tc.post(
        "/api/v1/doc-chunk/upload",
        params={"user_id": "user_001", "chunk_overlap": 20},
        files=[_txt_file()],
    )
    call_args = mock_uc.execute.call_args
    assert call_args[0][0].chunk_overlap == 20


def test_response_contains_request_id(client):
    tc, _ = client
    resp = tc.post(
        "/api/v1/doc-chunk/upload",
        params={"user_id": "user_001"},
        files=[_txt_file()],
    )
    data = resp.json()
    assert "request_id" in data
    assert data["request_id"]


# ──────────────────────────────────────────────────────
# 유효성 검증 실패
# ──────────────────────────────────────────────────────

def test_missing_user_id_returns_422(client):
    tc, _ = client
    resp = tc.post(
        "/api/v1/doc-chunk/upload",
        files=[_txt_file()],
    )
    assert resp.status_code == 422


def test_missing_file_returns_422(client):
    tc, _ = client
    resp = tc.post(
        "/api/v1/doc-chunk/upload",
        params={"user_id": "user_001"},
    )
    assert resp.status_code == 422


def test_invalid_strategy_returns_422(client):
    tc, _ = client
    resp = tc.post(
        "/api/v1/doc-chunk/upload",
        params={"user_id": "user_001", "strategy_type": "invalid_strategy"},
        files=[_txt_file()],
    )
    assert resp.status_code == 422


# ──────────────────────────────────────────────────────
# 비즈니스 에러 처리
# ──────────────────────────────────────────────────────

def test_unsupported_extension_returns_422():
    from src.api.routes.doc_chunk_router import router, get_doc_chunk_use_case

    app = FastAPI()
    app.include_router(router)

    mock_uc = MagicMock()
    mock_uc.execute = AsyncMock(side_effect=ValueError("Unsupported file type: '.zip'"))
    app.dependency_overrides[get_doc_chunk_use_case] = lambda: mock_uc

    tc = TestClient(app)
    resp = tc.post(
        "/api/v1/doc-chunk/upload",
        params={"user_id": "user_001"},
        files=[("file", ("archive.zip", io.BytesIO(b"fake"), "application/zip"))],
    )
    assert resp.status_code == 422
    assert "Unsupported file type" in resp.json()["detail"]


def test_use_case_called_with_correct_filename(client):
    tc, mock_uc = client
    tc.post(
        "/api/v1/doc-chunk/upload",
        params={"user_id": "user_001"},
        files=[_txt_file()],
    )
    call_args = mock_uc.execute.call_args
    assert call_args[0][0].filename == "test.txt"


def test_use_case_called_with_correct_user_id(client):
    tc, mock_uc = client
    tc.post(
        "/api/v1/doc-chunk/upload",
        params={"user_id": "user_abc"},
        files=[_txt_file()],
    )
    call_args = mock_uc.execute.call_args
    assert call_args[0][0].user_id == "user_abc"
