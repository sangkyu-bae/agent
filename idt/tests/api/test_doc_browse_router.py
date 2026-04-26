from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.doc_browse_router import (
    get_chunks_use_case,
    get_list_documents_use_case,
    router,
)
from src.domain.doc_browse.schemas import (
    ChunkDetail,
    DocumentChunksResult,
    DocumentSummary,
    ParentChunkGroup,
)


def _list_docs_mock(documents=None, total=None):
    docs = documents or []
    uc = MagicMock()
    uc.execute = AsyncMock(
        return_value={
            "collection_name": "test-col",
            "documents": docs,
            "total_documents": total if total is not None else len(docs),
            "offset": 0,
            "limit": 20,
        }
    )
    return uc


def _chunks_mock(result: DocumentChunksResult):
    uc = MagicMock()
    uc.execute = AsyncMock(return_value=result)
    return uc


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    return a


def test_list_documents_returns_200(app):
    docs = [
        DocumentSummary(
            document_id="doc-1",
            filename="a.pdf",
            category="policy",
            chunk_count=3,
            chunk_types=["child", "parent"],
            user_id="u1",
        ),
    ]
    mock_uc = _list_docs_mock(docs, total=1)
    app.dependency_overrides[get_list_documents_use_case] = lambda: mock_uc

    client = TestClient(app)
    resp = client.get("/api/v1/collections/test-col/documents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_documents"] == 1
    assert body["documents"][0]["document_id"] == "doc-1"


def test_list_documents_pagination(app):
    docs = [
        DocumentSummary(
            document_id=f"doc-{i}",
            filename=f"{i}.pdf",
            category="c",
            chunk_count=1,
            chunk_types=["full"],
            user_id="u",
        )
        for i in range(5)
    ]

    uc = MagicMock()
    uc.execute = AsyncMock(
        return_value={
            "collection_name": "col",
            "documents": docs[1:3],
            "total_documents": 5,
            "offset": 1,
            "limit": 2,
        }
    )
    app.dependency_overrides[get_list_documents_use_case] = lambda: uc

    client = TestClient(app)
    resp = client.get("/api/v1/collections/col/documents?offset=1&limit=2")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["documents"]) == 2
    assert body["total_documents"] == 5


def test_get_chunks_returns_200(app):
    result = DocumentChunksResult(
        document_id="doc-1",
        filename="a.pdf",
        chunk_strategy="parent_child",
        total_chunks=2,
        chunks=[
            ChunkDetail(
                chunk_id="c1",
                chunk_index=0,
                chunk_type="child",
                content="text 0",
                metadata={"category": "policy"},
            ),
            ChunkDetail(
                chunk_id="c2",
                chunk_index=1,
                chunk_type="child",
                content="text 1",
                metadata={"category": "policy"},
            ),
        ],
    )
    app.dependency_overrides[get_chunks_use_case] = lambda: _chunks_mock(result)

    client = TestClient(app)
    resp = client.get("/api/v1/collections/col/documents/doc-1/chunks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["chunk_strategy"] == "parent_child"
    assert len(body["chunks"]) == 2


def test_get_chunks_include_parent(app):
    result = DocumentChunksResult(
        document_id="doc-1",
        filename="a.pdf",
        chunk_strategy="parent_child",
        total_chunks=3,
        parents=[
            ParentChunkGroup(
                chunk_id="par1",
                chunk_index=0,
                chunk_type="parent",
                content="parent text",
                children=[
                    ChunkDetail(
                        chunk_id="ch1",
                        chunk_index=0,
                        chunk_type="child",
                        content="child text",
                        metadata={},
                    ),
                ],
            ),
        ],
    )
    app.dependency_overrides[get_chunks_use_case] = lambda: _chunks_mock(result)

    client = TestClient(app)
    resp = client.get(
        "/api/v1/collections/col/documents/doc-1/chunks?include_parent=true"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["parents"] is not None
    assert len(body["parents"]) == 1
    assert body["parents"][0]["chunk_id"] == "par1"
    assert len(body["parents"][0]["children"]) == 1


def test_get_chunks_nonexistent_document(app):
    result = DocumentChunksResult(
        document_id="no-doc",
        filename="unknown",
        chunk_strategy="unknown",
        total_chunks=0,
    )
    app.dependency_overrides[get_chunks_use_case] = lambda: _chunks_mock(result)

    client = TestClient(app)
    resp = client.get("/api/v1/collections/col/documents/no-doc/chunks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_chunks"] == 0
    assert body["chunks"] == []
