"""TC-P01~P14: PositionalReranker 정책 테스트."""
import pytest

from src.domain.reranker.interfaces import RerankerInterface
from src.domain.reranker.policies import PositionalReranker
from src.domain.reranker.schemas import RerankableDocument, RerankerRequest


def _make_docs(n: int) -> list[RerankableDocument]:
    """score 내림차순 문서 N개 생성. id는 1-indexed."""
    return [
        RerankableDocument(
            id=str(i + 1),
            content=f"문서 {i + 1}",
            score=round(1.0 - i * 0.05, 2),
        )
        for i in range(n)
    ]


def _ids(docs: list[RerankableDocument]) -> list[str]:
    return [d.id for d in docs]


class TestAlternatingEnds:
    """TC-P01~P06: 양끝 우선 배치 알고리즘 검증."""

    @pytest.mark.asyncio
    async def test_five_documents(self) -> None:
        """TC-P01: 5개 문서 → [1,3,5,4,2]."""
        reranker = PositionalReranker()
        docs = _make_docs(5)
        req = RerankerRequest(query="q", documents=docs, top_k=5)
        resp = await reranker.rerank(req)
        assert _ids(resp.documents) == ["1", "3", "5", "4", "2"]

    @pytest.mark.asyncio
    async def test_six_documents(self) -> None:
        """TC-P02: 6개 문서 → [1,3,5,6,4,2]."""
        reranker = PositionalReranker()
        docs = _make_docs(6)
        req = RerankerRequest(query="q", documents=docs, top_k=6)
        resp = await reranker.rerank(req)
        assert _ids(resp.documents) == ["1", "3", "5", "6", "4", "2"]

    @pytest.mark.asyncio
    async def test_three_documents(self) -> None:
        """TC-P03: 3개 문서 → [1,3,2]."""
        reranker = PositionalReranker()
        docs = _make_docs(3)
        req = RerankerRequest(query="q", documents=docs, top_k=3)
        resp = await reranker.rerank(req)
        assert _ids(resp.documents) == ["1", "3", "2"]

    @pytest.mark.asyncio
    async def test_empty_list(self) -> None:
        """TC-P04: 빈 목록 → 빈 결과."""
        reranker = PositionalReranker()
        req = RerankerRequest(query="q", documents=[], top_k=5)
        resp = await reranker.rerank(req)
        assert resp.documents == []
        assert resp.reranked_count == 0

    @pytest.mark.asyncio
    async def test_single_document(self) -> None:
        """TC-P05: 1개 문서 → 그대로 반환."""
        reranker = PositionalReranker()
        docs = _make_docs(1)
        req = RerankerRequest(query="q", documents=docs, top_k=1)
        resp = await reranker.rerank(req)
        assert _ids(resp.documents) == ["1"]
        assert resp.reranked_count == 1

    @pytest.mark.asyncio
    async def test_two_documents(self) -> None:
        """TC-P06: 2개 문서 → [1,2] 순서 유지."""
        reranker = PositionalReranker()
        docs = _make_docs(2)
        req = RerankerRequest(query="q", documents=docs, top_k=2)
        resp = await reranker.rerank(req)
        assert _ids(resp.documents) == ["1", "2"]


class TestTopKAndCandidates:
    """TC-P07~P10: top_k, rerank_candidates 파라미터 동작."""

    @pytest.mark.asyncio
    async def test_top_k_limits_output(self) -> None:
        """TC-P07: top_k=3이면 3개만 반환."""
        reranker = PositionalReranker()
        docs = _make_docs(5)
        req = RerankerRequest(query="q", documents=docs, top_k=3)
        resp = await reranker.rerank(req)
        assert len(resp.documents) == 3

    @pytest.mark.asyncio
    async def test_rerank_candidates_limits_processing(self) -> None:
        """TC-P08: candidates=5이면 상위 5개만 reranking."""
        reranker = PositionalReranker()
        docs = _make_docs(10)
        req = RerankerRequest(
            query="q", documents=docs, top_k=5, rerank_candidates=5,
        )
        resp = await reranker.rerank(req)
        assert resp.reranked_count == 5
        returned_ids = set(_ids(resp.documents))
        assert returned_ids.issubset({"1", "2", "3", "4", "5"})

    @pytest.mark.asyncio
    async def test_candidates_greater_than_docs(self) -> None:
        """TC-P09: candidates > 문서 수 → 전체 reranking."""
        reranker = PositionalReranker()
        docs = _make_docs(3)
        req = RerankerRequest(
            query="q", documents=docs, top_k=3, rerank_candidates=10,
        )
        resp = await reranker.rerank(req)
        assert resp.reranked_count == 3
        assert len(resp.documents) == 3

    @pytest.mark.asyncio
    async def test_top_k_greater_than_docs(self) -> None:
        """TC-P10: top_k > 문서 수 → 전체 반환."""
        reranker = PositionalReranker()
        docs = _make_docs(3)
        req = RerankerRequest(query="q", documents=docs, top_k=10)
        resp = await reranker.rerank(req)
        assert len(resp.documents) == 3


class TestMetadata:
    """TC-P11~P14: 응답 메타데이터 및 무결성."""

    @pytest.mark.asyncio
    async def test_strategy_name(self) -> None:
        """TC-P11: strategy == 'positional'."""
        reranker = PositionalReranker()
        docs = _make_docs(3)
        req = RerankerRequest(query="q", documents=docs, top_k=3)
        resp = await reranker.rerank(req)
        assert resp.strategy == "positional"

    @pytest.mark.asyncio
    async def test_no_documents_lost_or_duplicated(self) -> None:
        """TC-P12: 입력 문서 전부 출력에 포함, 중복 없음."""
        reranker = PositionalReranker()
        docs = _make_docs(7)
        req = RerankerRequest(query="q", documents=docs, top_k=7)
        resp = await reranker.rerank(req)
        input_ids = set(_ids(docs))
        output_ids = _ids(resp.documents)
        assert set(output_ids) == input_ids
        assert len(output_ids) == len(set(output_ids))

    def test_implements_reranker_interface(self) -> None:
        """TC-P13: RerankerInterface ABC 준수."""
        reranker = PositionalReranker()
        assert isinstance(reranker, RerankerInterface)

    @pytest.mark.asyncio
    async def test_counts_accuracy(self) -> None:
        """TC-P14: original_count / reranked_count 정확성."""
        reranker = PositionalReranker()
        docs = _make_docs(10)
        req = RerankerRequest(
            query="q", documents=docs, top_k=5, rerank_candidates=6,
        )
        resp = await reranker.rerank(req)
        assert resp.original_count == 10
        assert resp.reranked_count == 6
