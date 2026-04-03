"""RAGAgentRequest, DocumentSource, RAGAgentResponse 스키마 단위 테스트."""
import pytest

from src.domain.rag_agent.schemas import DocumentSource, RAGAgentRequest, RAGAgentResponse


class TestRAGAgentRequest:
    def test_default_top_k(self):
        req = RAGAgentRequest(query="테스트 질문", user_id="u-1")
        assert req.top_k == 5

    def test_custom_top_k(self):
        req = RAGAgentRequest(query="질문", user_id="u-1", top_k=10)
        assert req.top_k == 10

    def test_frozen(self):
        req = RAGAgentRequest(query="질문", user_id="u-1")
        with pytest.raises((AttributeError, TypeError)):
            req.query = "변경"  # type: ignore[misc]


class TestDocumentSource:
    def test_fields(self):
        ds = DocumentSource(
            content="내용", source="report.pdf", chunk_id="c-1", score=0.9
        )
        assert ds.content == "내용"
        assert ds.source == "report.pdf"
        assert ds.chunk_id == "c-1"
        assert ds.score == 0.9

    def test_frozen(self):
        ds = DocumentSource(
            content="내용", source="file.pdf", chunk_id="c-1", score=0.5
        )
        with pytest.raises((AttributeError, TypeError)):
            ds.content = "변경"  # type: ignore[misc]


class TestRAGAgentResponse:
    def test_with_internal_docs(self):
        ds = DocumentSource(
            content="내용", source="file.pdf", chunk_id="c-1", score=0.9
        )
        resp = RAGAgentResponse(
            query="질문",
            answer="답변",
            sources=[ds],
            used_internal_docs=True,
            request_id="req-1",
        )
        assert resp.answer == "답변"
        assert len(resp.sources) == 1
        assert resp.used_internal_docs is True

    def test_without_internal_docs(self):
        resp = RAGAgentResponse(
            query="질문",
            answer="직접 답변",
            sources=[],
            used_internal_docs=False,
            request_id="req-2",
        )
        assert resp.used_internal_docs is False
        assert resp.sources == []

    def test_frozen(self):
        resp = RAGAgentResponse(
            query="q", answer="a", sources=[], used_internal_docs=False, request_id="r"
        )
        with pytest.raises((AttributeError, TypeError)):
            resp.answer = "변경"  # type: ignore[misc]
