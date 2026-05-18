"""TC-S01~S06: Reranker 도메인 스키마 테스트."""
import pytest

from src.domain.reranker.schemas import (
    RerankableDocument,
    RerankerRequest,
    RerankerResponse,
)


class TestRerankableDocument:
    """TC-S01~S03."""

    def test_create_with_all_fields(self) -> None:
        """TC-S01: id, content, score, metadata 설정 정상."""
        doc = RerankableDocument(
            id="doc-1",
            content="테스트 문서 내용",
            score=0.95,
            metadata={"source": "test.pdf"},
        )
        assert doc.id == "doc-1"
        assert doc.content == "테스트 문서 내용"
        assert doc.score == 0.95
        assert doc.metadata == {"source": "test.pdf"}

    def test_frozen_immutability(self) -> None:
        """TC-S02: frozen=True 불변성 확인."""
        doc = RerankableDocument(id="doc-1", content="내용", score=0.9)
        with pytest.raises(AttributeError):
            doc.score = 0.5  # type: ignore[misc]

    def test_default_metadata_empty_dict(self) -> None:
        """TC-S03: metadata 기본값은 빈 dict."""
        doc = RerankableDocument(id="doc-1", content="내용", score=0.9)
        assert doc.metadata == {}


class TestRerankerRequest:
    """TC-S04~S05."""

    def test_default_values(self) -> None:
        """TC-S04: top_k=5, rerank_candidates=None 기본값."""
        docs = [RerankableDocument(id="1", content="a", score=0.9)]
        req = RerankerRequest(query="질문", documents=docs)
        assert req.top_k == 5
        assert req.rerank_candidates is None

    def test_custom_parameters(self) -> None:
        """TC-S05: 커스텀 파라미터 설정."""
        docs = [RerankableDocument(id="1", content="a", score=0.9)]
        req = RerankerRequest(
            query="질문",
            documents=docs,
            top_k=10,
            rerank_candidates=20,
        )
        assert req.top_k == 10
        assert req.rerank_candidates == 20


class TestRerankerResponse:
    """TC-S06."""

    def test_create_response(self) -> None:
        """TC-S06: 모든 필드 정상 설정."""
        docs = [RerankableDocument(id="1", content="a", score=0.9)]
        resp = RerankerResponse(
            documents=docs,
            strategy="positional",
            original_count=10,
            reranked_count=5,
        )
        assert resp.documents == docs
        assert resp.strategy == "positional"
        assert resp.original_count == 10
        assert resp.reranked_count == 5
