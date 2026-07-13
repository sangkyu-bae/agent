"""RoutedRetrievalUseCase — 3계층 하강 오케스트레이터 (Design D2/D8).

임베딩 1회 → ①문서 top-K → ②섹션 top-N(벡터+BM25 RRF) → ③rawchunk 확장
→ 부족 시 기존 하이브리드 폴백 보충(dedup). LLM 호출 0회.
흐름 제어만 담당 — 검증·폴백 판단·병합은 RoutedRetrievalPolicy(domain).
"""
from typing import Callable

from src.application.hybrid_search.use_case import HybridSearchUseCase
from src.domain.hybrid_search.schemas import (
    HybridSearchRequest,
    HybridSearchResult,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.routed_retrieval.interfaces import (
    ChunkExpanderInterface,
    DocumentRouterInterface,
    SectionRouterInterface,
)
from src.domain.routed_retrieval.policy import RoutedRetrievalPolicy
from src.domain.routed_retrieval.schemas import (
    RoutedChunk,
    RoutedParams,
    RoutedRetrievalResult,
    RoutedScope,
)
from src.domain.vector.interfaces import EmbeddingInterface


class RoutedRetrievalUseCase:
    def __init__(
        self,
        embedding: EmbeddingInterface,
        document_router: DocumentRouterInterface,
        section_router: SectionRouterInterface,
        chunk_expander: ChunkExpanderInterface,
        policy: RoutedRetrievalPolicy,
        hybrid_search_getter: Callable[[], HybridSearchUseCase] | None,
        logger: LoggerInterface,
    ) -> None:
        self._embedding = embedding
        self._document_router = document_router
        self._section_router = section_router
        self._chunk_expander = chunk_expander
        self._policy = policy
        # getter 주입 — lifespan 싱글턴 생성 순서와 무관 (inner_search_getter 선례)
        self._hybrid_search_getter = hybrid_search_getter
        self._logger = logger

    async def execute(
        self,
        query: str,
        scope: RoutedScope,
        params: RoutedParams,
        request_id: str,
    ) -> RoutedRetrievalResult:
        self._policy.validate_params(params)
        query_vector = await self._embedding.embed_text(query)

        documents, sections, routed = await self._descend(
            query, query_vector, scope, params, request_id
        )
        fallback_added = 0
        if self._policy.need_fallback(len(routed), params.top_k):
            fallback_hits = await self._run_fallback(
                query, scope, params, request_id
            )
            routed, fallback_added = self._policy.merge_fallback(
                routed, fallback_hits, params.top_k
            )

        self._logger.info(
            "Routed retrieval completed",
            request_id=request_id,
            collection_name=scope.collection_name,
            kb_id=scope.kb_id,
            document_candidates=len(documents),
            section_candidates=len(sections),
            routed_results=len(routed) - fallback_added,
            fallback_added=fallback_added,
            fallback_used=fallback_added > 0,
        )
        return RoutedRetrievalResult(
            query=query,
            results=routed,
            fallback_used=fallback_added > 0,
            fallback_count=fallback_added,
            document_candidates=len(documents),
            section_candidates=len(sections),
            request_id=request_id,
        )

    async def _descend(
        self,
        query: str,
        query_vector: list[float],
        scope: RoutedScope,
        params: RoutedParams,
        request_id: str,
    ) -> tuple[list, list, list[RoutedChunk]]:
        """①문서 → ②섹션 → ③확장 하강 — 문서 0건이면 즉시 빈 결과 (D2)."""
        documents = await self._document_router.route(
            query_vector, scope, params.doc_top_k, request_id
        )
        if not documents:
            return [], [], []
        sections = await self._section_router.route(
            query,
            query_vector,
            [d.document_id for d in documents],
            scope,
            params,
            request_id,
        )
        routed = await self._chunk_expander.expand(
            sections,
            {d.document_id: d for d in documents},
            scope,
            request_id,
        )
        return documents, sections, routed[: params.top_k]

    async def _run_fallback(
        self,
        query: str,
        scope: RoutedScope,
        params: RoutedParams,
        request_id: str,
    ) -> list[HybridSearchResult]:
        """기존 하이브리드 위임 — 실패는 라우팅 결과를 훼손하지 않음 (D8)."""
        if self._hybrid_search_getter is None:
            return []
        metadata_filter = {"kb_id": scope.kb_id} if scope.kb_id else {}
        request = HybridSearchRequest(
            query=query,
            top_k=params.top_k,
            metadata_filter=metadata_filter,
            collection_name=scope.collection_name,
        )
        try:
            response = await self._hybrid_search_getter().execute(
                request, request_id
            )
            return response.results
        except Exception as e:
            self._logger.warning(
                "Routed retrieval fallback failed, keeping routed results",
                exception=e,
                request_id=request_id,
            )
            return []
