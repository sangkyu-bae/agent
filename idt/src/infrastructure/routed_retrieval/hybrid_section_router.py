"""HybridSectionRouter — 2차 섹션 라우팅 (summary-routed-retrieval Design D4).

선별 문서 내 section_summary를 ⓐ Qdrant 벡터(document_id MatchAny)
ⓑ ES BM25(summary_text/summary_keywords)로 조회해 RRFFusionPolicy로 병합.
병합 키 = 요약 결정적 ID(Qdrant point id = ES _id, 2단계 D5의 3자 일치).
한쪽 소스 실패는 warning 후 다른 소스로 강등(graceful).
"""
from src.domain.elasticsearch.interfaces import (
    ElasticsearchRepositoryInterface,
)
from src.domain.elasticsearch.schemas import ESSearchQuery
from src.domain.hybrid_search.policies import RRFFusionPolicy
from src.domain.hybrid_search.schemas import HybridSearchResult, SearchHit
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.routed_retrieval.interfaces import SectionRouterInterface
from src.domain.routed_retrieval.schemas import (
    RoutedParams,
    RoutedScope,
    SectionCandidate,
)
from src.domain.vector.interfaces import VectorStoreInterface
from src.domain.vector.value_objects import SearchFilter
from src.infrastructure.routed_retrieval.payload_utils import (
    parse_keyword_list,
)

_SECTION_SUMMARY_CHUNK_TYPE = "section_summary"


class HybridSectionRouter(SectionRouterInterface):
    def __init__(
        self,
        vector_store: VectorStoreInterface,
        es_repo: ElasticsearchRepositoryInterface,
        es_index: str,
        rrf_policy: RRFFusionPolicy,
        logger: LoggerInterface,
    ) -> None:
        self._vector_store = vector_store
        self._es_repo = es_repo
        self._es_index = es_index
        self._rrf = rrf_policy
        self._logger = logger

    async def route(
        self,
        query: str,
        query_vector: list[float],
        document_ids: list[str],
        scope: RoutedScope,
        params: RoutedParams,
        request_id: str,
    ) -> list[SectionCandidate]:
        vector_hits = await self._fetch_vector(
            query_vector, document_ids, scope, params, request_id
        )
        bm25_hits = await self._fetch_bm25(
            query, document_ids, scope, params, request_id
        )
        merged = self._rrf.merge(
            bm25_hits=bm25_hits,
            vector_hits=vector_hits,
            top_k=params.section_top_n,
            k=params.rrf_k,
            bm25_weight=params.bm25_weight,
            vector_weight=params.vector_weight,
        )
        return self._to_candidates(merged, request_id)

    async def _fetch_vector(
        self, query_vector, document_ids, scope, params, request_id
    ) -> list[SearchHit]:
        try:
            docs = await self._vector_store.search_by_vector(
                vector=query_vector,
                top_k=params.section_top_n,
                filter=SearchFilter(
                    metadata={"chunk_type": _SECTION_SUMMARY_CHUNK_TYPE},
                    metadata_any={"document_id": list(document_ids)},
                ),
                collection_name=scope.collection_name,
            )
            return [
                SearchHit(
                    id=doc.id.value if hasattr(doc.id, "value") else str(doc.id),
                    content=doc.content,
                    metadata=doc.metadata or {},
                    raw_score=doc.score or 0.0,
                )
                for doc in docs
            ]
        except Exception as e:
            self._logger.warning(
                "Section vector search failed, degrading to BM25 only",
                exception=e,
                request_id=request_id,
            )
            return []

    async def _fetch_bm25(
        self, query, document_ids, scope, params, request_id
    ) -> list[SearchHit]:
        filters: list[dict] = [
            {"term": {"chunk_type": _SECTION_SUMMARY_CHUNK_TYPE}},
            {"terms": {"document_id": list(document_ids)}},
        ]
        if scope.kb_id:
            filters.append({"term": {"kb_id": scope.kb_id}})
        es_query = ESSearchQuery(
            index=self._es_index,
            query={
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "summary_text^1.5",
                                    "summary_keywords",
                                ],
                                "type": "most_fields",
                            }
                        }
                    ],
                    "filter": filters,
                }
            },
            size=params.section_top_n,
        )
        try:
            hits = await self._es_repo.search(es_query, request_id)
            return [
                SearchHit(
                    id=hit.id,
                    content=str(hit.source.get("summary_text", "")),
                    metadata={
                        k: str(v)
                        for k, v in hit.source.items()
                        if k not in ("summary_text",)
                    },
                    raw_score=hit.score,
                )
                for hit in hits
            ]
        except Exception as e:
            self._logger.warning(
                "Section BM25 search failed, degrading to vector only",
                exception=e,
                request_id=request_id,
            )
            return []

    def _to_candidates(
        self, merged: list[HybridSearchResult], request_id: str
    ) -> list[SectionCandidate]:
        candidates: list[SectionCandidate] = []
        for result in merged:
            md = result.metadata or {}
            section_ref = str(md.get("section_ref", "")).strip()
            if not section_ref:
                self._logger.warning(
                    "Section candidate skipped: missing section_ref",
                    request_id=request_id,
                )
                continue
            candidates.append(
                SectionCandidate(
                    section_ref=section_ref,
                    document_id=str(md.get("document_id", "")),
                    score=result.score,
                    summary=result.content,
                    clause_title=str(md.get("clause_title", "")),
                    keywords=parse_keyword_list(
                        md.get("keywords") or md.get("summary_keywords")
                    ),
                    vector_rank=result.vector_rank,
                    bm25_rank=result.bm25_rank,
                    source=result.source,
                )
            )
        return candidates
