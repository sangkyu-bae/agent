"""MorphIndex API router tests — use case mocked."""
import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from unittest.mock import AsyncMock, MagicMock

from src.api.routes.morph_index_router import router, get_morph_index_use_case
from src.domain.morph_index.schemas import DualIndexedChunk, MorphIndexResult


def _make_result(n: int = 2) -> MorphIndexResult:
    chunks = [
        DualIndexedChunk(
            chunk_id=f"cid-{i}",
            chunk_type="child",
            morph_keywords=["금융", "달리다"],
            content=f"청크 {i}",
            char_start=i * 10,
            char_end=i * 10 + 5,
            chunk_index=i,
        )
        for i in range(n)
    ]
    return MorphIndexResult(
        document_id="doc-1",
        user_id="user-1",
        total_chunks=n,
        qdrant_indexed=n,
        es_indexed=n,
        indexed_chunks=chunks,
        request_id="req-uuid",
    )


@pytest.fixture
def client():
    mock_use_case = MagicMock()
    mock_use_case.execute = AsyncMock(return_value=_make_result())

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_morph_index_use_case] = lambda: mock_use_case

    with TestClient(app) as c:
        yield c, mock_use_case


def test_upload_success_returns_200(client):
    c, _ = client
    resp = c.post(
        "/api/v1/morph-index/upload",
        json={
            "document_id": "doc-1",
            "content": "금융 정책 분석 텍스트",
            "user_id": "user-1",
        },
    )
    assert resp.status_code == 200


def test_upload_response_has_required_fields(client):
    c, _ = client
    resp = c.post(
        "/api/v1/morph-index/upload",
        json={"document_id": "doc-1", "content": "텍스트", "user_id": "u1"},
    )
    body = resp.json()
    assert "document_id" in body
    assert "total_chunks" in body
    assert "qdrant_indexed" in body
    assert "es_indexed" in body
    assert "indexed_chunks" in body
    assert "request_id" in body


def test_upload_indexed_chunk_has_morph_keywords(client):
    c, _ = client
    resp = c.post(
        "/api/v1/morph-index/upload",
        json={"document_id": "doc-1", "content": "텍스트", "user_id": "u1"},
    )
    chunk = resp.json()["indexed_chunks"][0]
    assert "morph_keywords" in chunk
    assert "char_start" in chunk
    assert "char_end" in chunk
    assert "chunk_index" in chunk


def test_invalid_strategy_type_returns_422(client):
    c, _ = client
    resp = c.post(
        "/api/v1/morph-index/upload",
        json={
            "document_id": "doc-1",
            "content": "텍스트",
            "user_id": "u1",
            "strategy_type": "invalid_strategy",
        },
    )
    assert resp.status_code == 422


def test_missing_content_returns_422(client):
    c, _ = client
    resp = c.post(
        "/api/v1/morph-index/upload",
        json={"document_id": "doc-1", "user_id": "u1"},
    )
    assert resp.status_code == 422


def test_use_case_value_error_returns_422(client):
    c, mock_uc = client
    mock_uc.execute = AsyncMock(side_effect=ValueError("invalid input"))
    resp = c.post(
        "/api/v1/morph-index/upload",
        json={"document_id": "doc-1", "content": "텍스트", "user_id": "u1"},
    )
    assert resp.status_code == 422


def test_qdrant_indexed_equals_total_chunks(client):
    c, _ = client
    resp = c.post(
        "/api/v1/morph-index/upload",
        json={"document_id": "doc-1", "content": "텍스트", "user_id": "u1"},
    )
    body = resp.json()
    assert body["qdrant_indexed"] == body["total_chunks"]


def test_source_field_optional(client):
    c, _ = client
    resp = c.post(
        "/api/v1/morph-index/upload",
        json={
            "document_id": "doc-1",
            "content": "텍스트",
            "user_id": "u1",
            "source": "report.pdf",
        },
    )
    assert resp.status_code == 200


def test_use_case_called_with_request_id(client):
    c, mock_uc = client
    c.post(
        "/api/v1/morph-index/upload",
        json={"document_id": "doc-1", "content": "텍스트", "user_id": "u1"},
    )
    mock_uc.execute.assert_called_once()
    _, request_id = mock_uc.execute.call_args[0]
    assert len(request_id) == 36  # UUID format
