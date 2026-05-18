"""Reranker 도메인 정책.

순수 도메인 로직: 외부 의존성 없음.
"""
from src.domain.reranker.interfaces import RerankerInterface
from src.domain.reranker.schemas import (
    RerankableDocument,
    RerankerRequest,
    RerankerResponse,
)


class PositionalReranker(RerankerInterface):
    """양끝 우선 배치(Alternating Ends) 전략.

    Lost in the Middle (Liu et al., 2023) 대응:
    관련도 상위 문서를 시작/끝에, 하위 문서를 중간에 배치한다.
    """

    STRATEGY_NAME: str = "positional"

    async def rerank(self, request: RerankerRequest) -> RerankerResponse:
        documents = request.documents
        original_count = len(documents)

        if original_count <= 1:
            return RerankerResponse(
                documents=documents[: request.top_k],
                strategy=self.STRATEGY_NAME,
                original_count=original_count,
                reranked_count=original_count,
            )

        candidates = self._select_candidates(
            documents, request.rerank_candidates,
        )
        reordered = self._alternating_ends(candidates)
        final = reordered[: request.top_k]

        return RerankerResponse(
            documents=final,
            strategy=self.STRATEGY_NAME,
            original_count=original_count,
            reranked_count=len(candidates),
        )

    def _select_candidates(
        self,
        documents: list[RerankableDocument],
        rerank_candidates: int | None,
    ) -> list[RerankableDocument]:
        if rerank_candidates is None or rerank_candidates >= len(documents):
            return list(documents)
        return list(documents[:rerank_candidates])

    def _alternating_ends(
        self,
        documents: list[RerankableDocument],
    ) -> list[RerankableDocument]:
        """양끝 우선 배치 알고리즘.

        입력 (score 순): [1등, 2등, 3등, 4등, 5등]
        출력 (위치 순): [1등, 3등, 5등, 4등, 2등]
        """
        n = len(documents)
        result: list[RerankableDocument | None] = [None] * n

        left = 0
        right = n - 1

        for i, doc in enumerate(documents):
            if i % 2 == 0:
                result[left] = doc
                left += 1
            else:
                result[right] = doc
                right -= 1

        return [doc for doc in result if doc is not None]
