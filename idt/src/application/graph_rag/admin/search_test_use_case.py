"""관리자 검색 테스트 — 그래프·하이브리드·결합 결과를 나란히 (Design §4.2 search-test).

- 관리자 본인 권한(KB 필터만)으로 실행한다. 일반 사용자 권한 흉내는 없다.
- 노출 단계 off 이면 409. admin_only·general 에서는 단계 검사 없이 동작한다.
- 주제 판정이 잘리지 않게 이 테스트에서만 시간 상한을 최대(5,000ms)로 쓴다.
- 하이브리드 검색은 처음 쓸 때 만든다(lazy). 실패해도 그래프 결과는 돌려준다.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any

from src.application.graph_rag.admin.inspect_use_case import ensure_stage_on
from src.domain.extension_hooks.events import SupplementalGrant, SupplementalQuery
from src.domain.graph_rag.interfaces import GraphSettingsReaderPort
from src.domain.graph_rag.retrieval import GraphSearchTrace
from src.domain.graph_rag.value_objects import MAX_RETRIEVAL_TIMEOUT_MS
from src.domain.hybrid_search.policies import RankedList, RRFFusionPolicy
from src.domain.hybrid_search.schemas import HybridSearchRequest
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_RRF_K = 60


@dataclass
class SearchTestResult:
    trace: GraphSearchTrace
    hybrid_hits: list = field(default_factory=list)
    fused_hits: list = field(default_factory=list)
    hybrid_error: str | None = None


class SearchTestUseCase:
    def __init__(
        self,
        *,
        reader: GraphSettingsReaderPort,
        source: Any,  # GraphRetrievalSource
        hybrid_factory: Callable[[], Any] | None,
        logger: LoggerInterface,
    ) -> None:
        self._reader = reader
        self._source = source
        self._hybrid_factory = hybrid_factory
        self._hybrid: Any = None
        self._logger = logger

    async def run(
        self,
        *,
        query: str,
        kb_id: str | None,
        collection_name: str | None,
        top_k: int,
        max_hops: int | None,
        request_id: str,
    ) -> SearchTestResult:
        await ensure_stage_on(self._reader)
        settings = replace(
            await self._reader.get(), retrieval_timeout_ms=MAX_RETRIEVAL_TIMEOUT_MS
        )
        hard = {"kb_id": kb_id} if kb_id else {}
        sq = SupplementalQuery(
            query=query,
            top_k=top_k,
            collection_name=collection_name,
            es_index=None,
            hard_filter=hard,
            lenient_filter={},
            grant=SupplementalGrant(caller_is_admin=True),
            request_id=request_id,
        )
        trace = await self._source.search_trace(sq, settings, max_hops=max_hops)
        result = SearchTestResult(trace=trace)
        started = time.perf_counter()
        try:
            result.hybrid_hits = await self._hybrid_search(
                query, hard, collection_name, top_k, request_id
            )
        except Exception as e:  # noqa: BLE001 — 그래프 결과는 그대로 보여 준다
            result.hybrid_error = f"{type(e).__name__}: {e}"[:300]
            self._logger.warning(
                "search-test hybrid failed", exception=e, request_id=request_id
            )
        trace.timings_ms["hybrid"] = int((time.perf_counter() - started) * 1000)
        result.fused_hits = RRFFusionPolicy().merge_many(
            [
                RankedList("primary", list(result.hybrid_hits), 1.0),
                RankedList("graph", list(trace.hits), settings.graph_rrf_weight),
            ],
            top_k=top_k,
            k=_RRF_K,
        )
        return result

    async def _hybrid_search(self, query, hard, collection_name, top_k, request_id):
        if self._hybrid_factory is None:
            raise RuntimeError("hybrid search not wired")
        if self._hybrid is None:
            self._hybrid = self._hybrid_factory()
        response = await self._hybrid.execute(
            HybridSearchRequest(
                query=query,
                top_k=top_k,
                bm25_top_k=top_k * 2,
                vector_top_k=top_k * 2,
                rrf_k=_RRF_K,
                metadata_filter=dict(hard),
                collection_name=collection_name,
            ),
            request_id,
        )
        return list(response.results)
