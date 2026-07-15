"""KB 저장 내용 조회 엔드포인트 3종 라우터 테스트 — kb-content-browser Design §4.3.

200/404/403, source 검증(422), 파라미터 위임 확인.
"""
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.api.routes.knowledge_base_router import (
    get_kb_document_chunks_use_case,
    get_kb_document_summary_use_case,
    get_kb_section_summaries_use_case,
    router,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.doc_browse.schemas import ChunkDetail, ParentChunkGroup
from src.domain.knowledge_base.browse_schemas import (
    KbDocumentChunksResult,
    KbDocumentSummaryResult,
    KbSectionSummaryItem,
    KbSectionSummaryListResult,
)

KB_ID = "kb-1"
DOC_ID = "doc-1"
BASE = f"/api/v1/knowledge-bases/{KB_ID}/documents/{DOC_ID}"


@pytest.fixture
def mock_summary_uc() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_sections_uc() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_chunks_uc() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(mock_summary_uc, mock_sections_uc, mock_chunks_uc) -> TestClient:
    from fastapi import FastAPI

    from src.interfaces.dependencies.auth import get_current_user

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_kb_document_summary_use_case] = (
        lambda: mock_summary_uc
    )
    app.dependency_overrides[get_kb_section_summaries_use_case] = (
        lambda: mock_sections_uc
    )
    app.dependency_overrides[get_kb_document_chunks_use_case] = (
        lambda: mock_chunks_uc
    )
    app.dependency_overrides[get_current_user] = lambda: User(
        id=1,
        email="t@t.com",
        password_hash="h",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
    )
    return TestClient(app)


class TestDocumentSummary:
    def test_returns_200(self, client, mock_summary_uc):
        mock_summary_uc.execute.return_value = KbDocumentSummaryResult(
            exists=True,
            source="qdrant",
            chunk_id="ds-1",
            summary_text="문서 요약",
            keywords=["여신"],
            section_count=3,
            filename="a.pdf",
            metadata={"kb_id": KB_ID},
        )
        resp = client.get(f"{BASE}/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is True
        assert data["summary_text"] == "문서 요약"
        assert data["section_count"] == 3
        # 기본 source=qdrant (D2)
        assert mock_summary_uc.execute.await_args.args[2] == "qdrant"

    def test_source_es_forwarded(self, client, mock_summary_uc):
        mock_summary_uc.execute.return_value = KbDocumentSummaryResult(
            exists=False, source="es"
        )
        resp = client.get(f"{BASE}/summary?source=es")
        assert resp.status_code == 200
        assert resp.json()["exists"] is False
        assert mock_summary_uc.execute.await_args.args[2] == "es"

    def test_invalid_source_returns_422(self, client):
        resp = client.get(f"{BASE}/summary?source=redis")
        assert resp.status_code == 422

    def test_not_found_returns_404(self, client, mock_summary_uc):
        mock_summary_uc.execute.side_effect = ValueError(
            f"Document '{DOC_ID}' not found in knowledge base '{KB_ID}'"
        )
        resp = client.get(f"{BASE}/summary")
        assert resp.status_code == 404

    def test_permission_denied_returns_403(self, client, mock_summary_uc):
        mock_summary_uc.execute.side_effect = PermissionError("No read access")
        resp = client.get(f"{BASE}/summary")
        assert resp.status_code == 403


class TestSectionSummaries:
    def test_returns_200(self, client, mock_sections_uc):
        mock_sections_uc.execute.return_value = KbSectionSummaryListResult(
            source="es",
            document_id=DOC_ID,
            total=1,
            items=[
                KbSectionSummaryItem(
                    chunk_id="ss-1",
                    section_ref="ref-1",
                    clause_title="제1장",
                    chunk_index=0,
                    summary_text="섹션 요약",
                    keywords=["규정"],
                    metadata={"kb_id": KB_ID},
                )
            ],
        )
        resp = client.get(f"{BASE}/section-summaries?source=es")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["clause_title"] == "제1장"
        assert data["items"][0]["summary_text"] == "섹션 요약"

    def test_not_found_returns_404(self, client, mock_sections_uc):
        mock_sections_uc.execute.side_effect = ValueError("not found")
        resp = client.get(f"{BASE}/section-summaries")
        assert resp.status_code == 404


class TestDocumentChunks:
    def test_returns_200_with_hierarchy(self, client, mock_chunks_uc):
        child = ChunkDetail(
            chunk_id="ch1",
            chunk_index=0,
            chunk_type="child",
            content="본문",
            metadata={"kb_id": KB_ID},
        )
        mock_chunks_uc.execute.return_value = KbDocumentChunksResult(
            source="qdrant",
            search_mode=None,
            document_id=DOC_ID,
            filename="a.pdf",
            chunk_strategy="parent_child",
            total_chunks=2,
            parents=[
                ParentChunkGroup(
                    chunk_id="par1",
                    chunk_index=0,
                    chunk_type="parent",
                    content="부모 본문",
                    children=[child],
                )
            ],
        )
        resp = client.get(f"{BASE}/chunks?include_parent=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["parents"][0]["chunk_id"] == "par1"
        assert data["parents"][0]["children"][0]["content"] == "본문"
        assert data["search_mode"] is None

    def test_query_params_forwarded(self, client, mock_chunks_uc):
        mock_chunks_uc.execute.return_value = KbDocumentChunksResult(
            source="es",
            search_mode="match",
            document_id=DOC_ID,
            filename="a.pdf",
            chunk_strategy="parent_child",
            total_chunks=0,
        )
        resp = client.get(f"{BASE}/chunks?source=es&q=담보&include_parent=false")
        assert resp.status_code == 200
        assert resp.json()["search_mode"] == "match"
        args = mock_chunks_uc.execute.await_args.args
        assert args[2] == "es"
        assert args[3] is False
        assert args[4] == "담보"

    def test_invalid_source_returns_422(self, client):
        resp = client.get(f"{BASE}/chunks?source=mongo")
        assert resp.status_code == 422

    def test_permission_denied_returns_403(self, client, mock_chunks_uc):
        mock_chunks_uc.execute.side_effect = PermissionError("No read access")
        resp = client.get(f"{BASE}/chunks")
        assert resp.status_code == 403
