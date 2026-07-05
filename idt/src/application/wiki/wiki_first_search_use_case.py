"""WikiFirstSearchUseCase: 위키 우선 검색 + 원본 폴백 (LLM-WIKI-001, Phase 1/B).

승인+미만료 위키 항목을 우선 노출하고, top_k에 미달할 때만 기존
HybridSearchUseCase로 폴백해 원본 청크를 보충한다. 기존 검색 UseCase는
수정하지 않고 래핑한다(테스트 회귀 방지, SRP).
"""
from datetime import datetime

from src.application.repositories.wiki_repository import WikiArticleRepository
from src.domain.hybrid_search.schemas import (
    HybridSearchRequest,
    HybridSearchResponse,
    HybridSearchResult,
)
from src.domain.wiki.entity import WikiArticle


class WikiFirstSearchUseCase:
    """위키(정제 지식)를 우선하고 부족분만 원본으로 폴백하는 검색."""

    def __init__(
        self,
        wiki_repo: WikiArticleRepository,
        inner_search,  # HybridSearchUseCase (duck-typed: .execute(request, request_id))
    ) -> None:
        self._wiki_repo = wiki_repo
        self._inner = inner_search

    async def execute(
        self,
        request: HybridSearchRequest,
        agent_id: str,
        now: datetime,
        request_id: str,
    ) -> HybridSearchResponse:
        articles = await self._wiki_repo.search_similar(
            agent_id, request.query, request.top_k, now, request_id
        )
        wiki_results = [self._to_result(a) for a in articles]

        if len(wiki_results) >= request.top_k:
            return self._response(request, wiki_results[: request.top_k], request_id)

        fallback = await self._inner.execute(request, request_id)
        merged = self._merge(wiki_results, fallback.results, request.top_k)
        return self._response(request, merged, request_id)

    @staticmethod
    def _merge(
        wiki_results: list[HybridSearchResult],
        fallback_results: list[HybridSearchResult],
        top_k: int,
    ) -> list[HybridSearchResult]:
        """위키 우선 + 폴백 보충. id 중복 시 위키 것을 유지."""
        seen = {r.id for r in wiki_results}
        merged = list(wiki_results)
        for r in fallback_results:
            if r.id not in seen:
                merged.append(r)
                seen.add(r.id)
        return merged[:top_k]

    @staticmethod
    def _to_result(article: WikiArticle) -> HybridSearchResult:
        """위키 항목을 검색 결과 표현으로 변환(source='wiki')."""
        return HybridSearchResult(
            id=article.id,
            content=article.content,
            score=article.confidence,
            bm25_rank=None,
            bm25_score=None,
            vector_rank=None,
            vector_score=None,
            source="wiki",
            metadata={
                "title": article.title,
                "source_type": article.source_type.value,
                "status": article.status.value,
                "agent_id": article.agent_id,
                "wiki": "true",
            },
        )

    @staticmethod
    def _response(
        request: HybridSearchRequest,
        results: list[HybridSearchResult],
        request_id: str,
    ) -> HybridSearchResponse:
        return HybridSearchResponse(
            query=request.query,
            results=results,
            total_found=len(results),
            request_id=request_id,
        )
