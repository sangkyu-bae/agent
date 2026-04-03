"""Tests for chunk-and-index API router."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI


def _make_mock_use_case():
    from src.application.chunk_and_index.schemas import ChunkAndIndexResult, IndexedChunk
    uc = MagicMock()
    uc.execute = AsyncMock(
        return_value=ChunkAndIndexResult(
            document_id="doc-1",
            user_id="u1",
            total_chunks=2,
            indexed_chunks=[
                IndexedChunk(chunk_id="c1", chunk_type="child", keywords=["금융", "정책"], content="청크1"),
                IndexedChunk(chunk_id="c2", chunk_type="child", keywords=["이자율"], content="청크2"),
            ],
            request_id="req-123",
        )
    )
    return uc


@pytest.fixture
def client():
    from src.api.routes.chunk_index_router import router, get_chunk_index_use_case
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_chunk_index_use_case] = lambda: _make_mock_use_case()
    return TestClient(app)


VALID_BODY = {
    "document_id": "doc-1",
    "content": "금융 정책 이자율에 대한 문서 내용입니다.",
    "user_id": "user-1",
    "strategy_type": "parent_child",
}


class TestChunkIndexRouter:
    def test_upload_returns_200(self, client):
        resp = client.post("/api/v1/chunk-index/upload", json=VALID_BODY)
        assert resp.status_code == 200

    def test_response_contains_total_chunks(self, client):
        resp = client.post("/api/v1/chunk-index/upload", json=VALID_BODY)
        assert resp.json()["total_chunks"] == 2

    def test_response_contains_indexed_chunks(self, client):
        resp = client.post("/api/v1/chunk-index/upload", json=VALID_BODY)
        chunks = resp.json()["indexed_chunks"]
        assert len(chunks) == 2

    def test_indexed_chunk_has_keywords(self, client):
        resp = client.post("/api/v1/chunk-index/upload", json=VALID_BODY)
        first_chunk = resp.json()["indexed_chunks"][0]
        assert "keywords" in first_chunk
        assert "금융" in first_chunk["keywords"]

    def test_indexed_chunk_has_chunk_type(self, client):
        resp = client.post("/api/v1/chunk-index/upload", json=VALID_BODY)
        first_chunk = resp.json()["indexed_chunks"][0]
        assert first_chunk["chunk_type"] == "child"

    def test_missing_document_id_returns_422(self, client):
        resp = client.post("/api/v1/chunk-index/upload", json={"content": "텍스트", "user_id": "u1"})
        assert resp.status_code == 422

    def test_missing_content_returns_422(self, client):
        resp = client.post("/api/v1/chunk-index/upload", json={"document_id": "d1", "user_id": "u1"})
        assert resp.status_code == 422

    def test_custom_top_keywords_accepted(self, client):
        body = {**VALID_BODY, "top_keywords": 5}
        resp = client.post("/api/v1/chunk-index/upload", json=body)
        assert resp.status_code == 200

    def test_response_includes_document_id(self, client):
        resp = client.post("/api/v1/chunk-index/upload", json=VALID_BODY)
        assert resp.json()["document_id"] == "doc-1"
