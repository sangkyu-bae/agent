"""EsEvidenceFetcher — 그래프가 고른 청크를 ES 에서 권한 필터를 걸어 다시 읽는다.

Design Ref: graph-rag-foundation §2.2 검색, Plan FR-12. ES _id = chunk_id.
필터는 하이브리드 BM25 경로와 같은 규칙이다: hard = term, lenient = "값 일치 OR 필드
부재", collection_name 이 있으면 컬렉션 격리. 권한 밖 청크는 여기서 빠진다.
"""

from __future__ import annotations

from typing import Any

from src.domain.elasticsearch.schemas import ESSearchQuery
from src.domain.graph_rag.interfaces import EvidenceFetcherPort
from src.domain.hybrid_search.schemas import HybridSearchResult
from src.domain.logging.interfaces.logger_interface import LoggerInterface

GRAPH_SOURCE = "graph"


def build_filters(
    hard_filter: dict, lenient_filter: dict, collection_name: str | None
) -> list[dict]:
    clauses: list[dict] = [{"term": {k: v}} for k, v in hard_filter.items()]
    for key, value in lenient_filter.items():
        clauses.append(
            {
                "bool": {
                    "should": [
                        {"term": {key: value}},
                        {"bool": {"must_not": [{"exists": {"field": key}}]}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
    if collection_name:
        clauses.append({"term": {"collection_name": collection_name}})
    return clauses


class EsEvidenceFetcher(EvidenceFetcherPort):
    def __init__(self, es_repo: Any, default_index: str, logger: LoggerInterface):
        self._es_repo = es_repo
        self._default_index = default_index
        self._logger = logger

    async def fetch(
        self,
        chunk_ids: list[str],
        *,
        hard_filter: dict,
        lenient_filter: dict,
        collection_name: str | None,
        es_index: str | None,
        request_id: str,
    ) -> list[HybridSearchResult]:
        if not chunk_ids:
            return []
        filters = [{"ids": {"values": list(chunk_ids)}}]
        filters += build_filters(hard_filter, lenient_filter, collection_name)
        hits = await self._es_repo.search(
            ESSearchQuery(
                index=es_index or self._default_index,
                query={"bool": {"filter": filters}},
                size=len(chunk_ids),
            ),
            request_id,
        )
        return [
            HybridSearchResult(
                id=h.id,
                content=str(h.source.get("content", "")),
                score=0.0,
                bm25_rank=None,
                bm25_score=None,
                vector_rank=None,
                vector_score=None,
                source=GRAPH_SOURCE,
                metadata={k: str(v) for k, v in h.source.items() if k != "content"},
            )
            for h in hits
        ]
