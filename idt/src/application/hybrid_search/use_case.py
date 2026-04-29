"""HybridSearchUseCase: BM25(ES) + Vector(Qdrant) → RRF 병합."""
from src.domain.elasticsearch.interfaces import ElasticsearchRepositoryInterface
from src.domain.elasticsearch.schemas import ESSearchQuery
from src.domain.hybrid_search.policies import RRFFusionPolicy
from src.domain.hybrid_search.schemas import (
    HybridSearchRequest,
    HybridSearchResponse,
    SearchHit,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.vector.interfaces import EmbeddingInterface, VectorStoreInterface


class HybridSearchUseCase:
    """BM25 + 벡터 검색 결과를 RRF로 병합하여 반환하는 UseCase."""

    def __init__(
        self,
        es_repo: ElasticsearchRepositoryInterface,
        embedding: EmbeddingInterface,
        vector_store: VectorStoreInterface,
        es_index: str,
        logger: LoggerInterface,
    ) -> None:
        self._es_repo = es_repo
        self._embedding = embedding
        self._vector_store = vector_store
        self._es_index = es_index
        self._logger = logger
        self._rrf_policy = RRFFusionPolicy()

    async def execute(
        self, request: HybridSearchRequest, request_id: str
    ) -> HybridSearchResponse:
        """하이브리드 검색 실행.

        Args:
            request: 검색 요청 파라미터
            request_id: 요청 추적 ID

        Returns:
            RRF 병합된 검색 결과
        """
        self._logger.info(
            "HybridSearch started",
            request_id=request_id,
            query=request.query,
            bm25_top_k=request.bm25_top_k,
            vector_top_k=request.vector_top_k,
        )
        try:
            bm25_hits, vector_hits = await self._fetch_both(request, request_id)

            results = self._rrf_policy.merge(
                bm25_hits=bm25_hits,
                vector_hits=vector_hits,
                top_k=request.top_k,
                k=request.rrf_k,
                bm25_weight=request.bm25_weight,
                vector_weight=request.vector_weight,
            )

            self._logger.info(
                "HybridSearch completed",
                request_id=request_id,
                total_results=len(results),
            )
            return HybridSearchResponse(
                query=request.query,
                results=results,
                total_found=len(results),
                request_id=request_id,
            )
        except Exception as e:
            self._logger.error(
                "HybridSearch failed", exception=e, request_id=request_id
            )
            raise

    async def _fetch_both(
        self, request: HybridSearchRequest, request_id: str
    ) -> tuple[list[SearchHit], list[SearchHit]]:
        """BM25와 벡터 검색을 독립 실행하고 SearchHit 목록으로 변환."""
        bm25_hits = await self._fetch_bm25(request, request_id)
        vector_hits = await self._fetch_vector(request, request_id)
        return bm25_hits, vector_hits

    async def _fetch_bm25(
        self, request: HybridSearchRequest, request_id: str
    ) -> list[SearchHit]:
        try:
            multi_match_clause: dict = {
                "multi_match": {
                    "query": request.query,
                    "fields": ["content", "morph_text^1.5"],
                    "type": "most_fields",
                }
            }
            es_query_body: dict = multi_match_clause
            if request.metadata_filter:
                filter_clauses = [
                    {"term": {k: v}} for k, v in request.metadata_filter.items()
                ]
                es_query_body = {
                    "bool": {
                        "must": [multi_match_clause],
                        "filter": filter_clauses,
                    },
                }
            es_query = ESSearchQuery(
                index=self._es_index,
                query=es_query_body,
                size=request.bm25_top_k,
            )
            es_results = await self._es_repo.search(es_query, request_id)
            return [
                SearchHit(
                    id=hit.id,
                    content=hit.source.get("content", ""),
                    metadata={
                        k: str(v) for k, v in hit.source.items() if k != "content"
                    },
                    raw_score=hit.score,
                )
                for hit in es_results
            ]
        except Exception as e:
            self._logger.warning(
                "BM25 search failed, falling back to empty",
                exception=e,
                request_id=request_id,
            )
            return []

    async def _fetch_vector(
        self, request: HybridSearchRequest, request_id: str
    ) -> list[SearchHit]:
        try:
            query_vector = await self._embedding.embed_text(request.query)
            vector_filter = None
            if request.metadata_filter:
                from src.domain.vector.value_objects import SearchFilter
                vector_filter = SearchFilter(metadata=request.metadata_filter)
            vector_docs = await self._vector_store.search_by_vector(
                vector=query_vector,
                top_k=request.vector_top_k,
                filter=vector_filter,
            )
            return [
                SearchHit(
                    id=doc.id.value if hasattr(doc.id, "value") else str(doc.id),
                    content=doc.content,
                    metadata=doc.metadata,
                    raw_score=doc.score or 0.0,
                )
                for doc in vector_docs
            ]
        except Exception as e:
            self._logger.warning(
                "Vector search failed, falling back to empty",
                exception=e,
                request_id=request_id,
            )
            return []
