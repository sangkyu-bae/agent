"""RAG Agent API 엔드포인트 단위 테스트."""
import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.rag_agent_router import router, get_rag_agent_use_case
from src.domain.rag_agent.schemas import DocumentSource, RAGAgentResponse


def _build_app(mock_uc) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_rag_agent_use_case] = lambda: mock_uc
    return app


def _ok_response(
    query: str = "금융 정책",
    answer: str = "답변입니다.",
    sources: list | None = None,
    used: bool = True,
    req_id: str = "req-1",
) -> RAGAgentResponse:
    if sources is None:
        sources = [
            DocumentSource(
                content="내용", source="report.pdf", chunk_id="c-1", score=0.9
            )
        ]
    return RAGAgentResponse(
        query=query,
        answer=answer,
        sources=sources,
        used_internal_docs=used,
        request_id=req_id,
    )


class TestRAGAgentRouter:
    def test_query_returns_200(self):
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = _ok_response()

        client = TestClient(_build_app(mock_uc))
        resp = client.post(
            "/api/v1/rag-agent/query",
            json={"query": "금융 정책", "user_id": "u-1"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["answer"] == "답변입니다."
        assert data["used_internal_docs"] is True
        assert len(data["sources"]) == 1
        assert data["sources"][0]["source"] == "report.pdf"

    def test_query_no_internal_docs(self):
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = _ok_response(
            query="안녕", answer="안녕하세요!", sources=[], used=False
        )

        client = TestClient(_build_app(mock_uc))
        resp = client.post(
            "/api/v1/rag-agent/query",
            json={"query": "안녕하세요", "user_id": "u-1"},
        )

        assert resp.status_code == 200
        assert resp.json()["used_internal_docs"] is False

    def test_empty_query_returns_422(self):
        mock_uc = AsyncMock()
        client = TestClient(_build_app(mock_uc))
        resp = client.post(
            "/api/v1/rag-agent/query",
            json={"query": "", "user_id": "u-1"},
        )
        assert resp.status_code == 422

    def test_missing_user_id_returns_422(self):
        mock_uc = AsyncMock()
        client = TestClient(_build_app(mock_uc))
        resp = client.post(
            "/api/v1/rag-agent/query",
            json={"query": "질문"},
        )
        assert resp.status_code == 422

    def test_value_error_returns_422(self):
        mock_uc = AsyncMock()
        mock_uc.execute.side_effect = ValueError("잘못된 요청")
        client = TestClient(_build_app(mock_uc))
        resp = client.post(
            "/api/v1/rag-agent/query",
            json={"query": "질문", "user_id": "u-1"},
        )
        assert resp.status_code == 422

    def test_custom_top_k_is_passed_to_use_case(self):
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = _ok_response(used=False, sources=[])
        client = TestClient(_build_app(mock_uc))
        client.post(
            "/api/v1/rag-agent/query",
            json={"query": "q", "user_id": "u", "top_k": 3},
        )
        call_request = mock_uc.execute.call_args[0][0]
        assert call_request.top_k == 3

    def test_default_top_k_is_5(self):
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = _ok_response(used=False, sources=[])
        client = TestClient(_build_app(mock_uc))
        client.post(
            "/api/v1/rag-agent/query",
            json={"query": "q", "user_id": "u"},
        )
        call_request = mock_uc.execute.call_args[0][0]
        assert call_request.top_k == 5

    def test_response_includes_request_id(self):
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = _ok_response(req_id="req-xyz", used=False, sources=[])
        client = TestClient(_build_app(mock_uc))
        resp = client.post(
            "/api/v1/rag-agent/query",
            json={"query": "q", "user_id": "u"},
        )
        assert "request_id" in resp.json()

    def test_sources_fields_in_response(self):
        mock_uc = AsyncMock()
        mock_uc.execute.return_value = _ok_response()
        client = TestClient(_build_app(mock_uc))
        resp = client.post(
            "/api/v1/rag-agent/query",
            json={"query": "q", "user_id": "u"},
        )
        src = resp.json()["sources"][0]
        assert "content" in src
        assert "source" in src
        assert "chunk_id" in src
        assert "score" in src
