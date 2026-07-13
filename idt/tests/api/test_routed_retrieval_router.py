"""Routed Retrieval 라우터 테스트 (summary-routed-retrieval Design D7)."""
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.api.routes.routed_retrieval_router import (
    get_routed_retrieval_use_case,
    router,
)
from src.domain.routed_retrieval.schemas import (
    DocumentCandidate,
    RoutedChunk,
    RoutedRetrievalResult,
    SectionCandidate,
)


@pytest.fixture
def mock_use_case() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(mock_use_case: AsyncMock) -> TestClient:
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_routed_retrieval_use_case] = (
        lambda: mock_use_case
    )
    return TestClient(app)


def _result() -> RoutedRetrievalResult:
    document = DocumentCandidate(
        document_id="doc-1", score=0.9, summary="문서 요약",
        keywords=["대출"], filename="rule.pdf",
    )
    section = SectionCandidate(
        section_ref="p1", document_id="doc-1", score=0.03,
        summary="섹션 요약", clause_title="제1조", keywords=["한도"],
        vector_rank=1, bm25_rank=2, source="both",
    )
    routed = RoutedChunk(
        section_ref="p1", document_id="doc-1", content="조 본문",
        score=0.03, clause_title="제1조", document=document, section=section,
    )
    fallback = RoutedChunk(
        section_ref="c9", document_id="doc-2", content="폴백 본문",
        score=0.01, from_fallback=True,
    )
    return RoutedRetrievalResult(
        query="여신 한도", results=[routed, fallback],
        fallback_used=True, fallback_count=1,
        document_candidates=3, section_candidates=7, request_id="req-1",
    )


def test_returns_200_with_routing_evidence(client, mock_use_case):
    mock_use_case.execute.return_value = _result()

    resp = client.post(
        "/api/v1/retrieval/routed",
        json={"query": "여신 한도", "kb_id": "kb-1", "top_k": 5},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["total_found"] == 2
    assert data["fallback_used"] is True
    assert data["document_candidates"] == 3

    first = data["results"][0]
    assert first["content"] == "조 본문"
    assert first["document"]["summary"] == "문서 요약"
    assert first["section"]["clause_title"] == "제1조"
    assert first["section"]["source"] == "both"
    assert first["from_fallback"] is False

    second = data["results"][1]
    assert second["from_fallback"] is True
    assert second["document"] is None
    assert second["section"] is None

    # 파라미터 매핑 확인
    _, scope, params, _ = mock_use_case.execute.call_args[0]
    assert scope.kb_id == "kb-1"
    assert params.top_k == 5


def test_field_validation_returns_422(client):
    resp = client.post(
        "/api/v1/retrieval/routed",
        json={"query": "q", "doc_top_k": 0},
    )
    assert resp.status_code == 422


def test_use_case_value_error_returns_422(client, mock_use_case):
    mock_use_case.execute.side_effect = ValueError("top_k must be 1~30")
    resp = client.post("/api/v1/retrieval/routed", json={"query": "q"})
    assert resp.status_code == 422


def test_defaults_applied(client, mock_use_case):
    mock_use_case.execute.return_value = RoutedRetrievalResult(
        query="q", results=[], fallback_used=False, fallback_count=0,
        document_candidates=0, section_candidates=0, request_id="r",
    )
    resp = client.post("/api/v1/retrieval/routed", json={"query": "q"})
    assert resp.status_code == 200
    _, scope, params, _ = mock_use_case.execute.call_args[0]
    assert scope.collection_name is None
    assert params.doc_top_k == 5
    assert params.section_top_n == 10
    assert params.top_k == 5
