"""GraphRetrievalSource — 대화 검색 도구의 보조 검색 공급자(그래프).

Design Ref: graph-rag-foundation §2.2 검색·§11.9 질문 주제, Plan FR-12~14·FR-29.
  단계 검사(RolloutPolicy × 호출자 grant)
  → [동시] 질문 주제(범위, 시간 상한의 절반)
          / 후보 엔티티 20개(Kiwi 명사 묶음 정확·별칭 + 질문 벡터, 범위 없이)
  → 범위 안 후보를 우선해 씨앗 5개(범위 안 후보가 없으면 범위를 풀고 진행)
  → 범위 안 관계만 따라 최대 N단계 경로(허브 노드 경유 금지)
  → 근거 청크 점수 → 주제 범위로 거르기(범위 안 근거가 0이면 범위 없이 다시 탐색)
  → ES 권한 재조회(도구의 hard/lenient 필터·컬렉션 그대로) → 상위 top_k.
실패·시간 초과·미실행은 예외 대신 skip_reason 으로 돌려준다(도구는 기존 결과만 쓴다).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace

from src.domain.extension_hooks.events import SupplementalQuery, SupplementalResult
from src.domain.extension_hooks.ports import SupplementalRetrievalSource
from src.domain.graph_rag.exceptions import GraphBackendUnavailableError
from src.domain.graph_rag.extraction import GLOBAL_SCOPE
from src.domain.graph_rag.interfaces import (
    EntityEmbedderPort,
    EvidenceFetcherPort,
    GraphSettingsReaderPort,
    GraphStorePort,
)
from src.domain.graph_rag.policies import RolloutPolicy
from src.domain.graph_rag.retrieval import (
    HUB_DEGREE_LIMIT,
    LINK_CANDIDATES,
    MAX_PATHS,
    MAX_SEEDS,
    GraphSearchTrace,
    QueryScope,
    RetrievalPolicy,
)
from src.domain.graph_rag.value_objects import GraphRagSettings
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.morph.interfaces import MorphAnalyzerInterface

GRAPH_LABEL = "graph"
_ROUTE_BUDGET_SHARE = 0.5


class GraphRetrievalSource(SupplementalRetrievalSource):
    def __init__(
        self,
        *,
        reader: GraphSettingsReaderPort,
        store: GraphStorePort,
        embedder: EntityEmbedderPort,
        morph: MorphAnalyzerInterface,
        router,  # QueryTopicRouter
        fetcher: EvidenceFetcherPort,
        logger: LoggerInterface,
    ) -> None:
        self._reader = reader
        self._store = store
        self._embedder = embedder
        self._morph = morph
        self._router = router
        self._fetcher = fetcher
        self._logger = logger

    async def retrieve(self, query: SupplementalQuery) -> SupplementalResult:
        settings = await self._reader.get()
        reason = RolloutPolicy.skip_reason(
            settings.rollout_stage, caller_is_admin=query.grant.caller_is_admin
        )
        if reason is not None:
            return SupplementalResult(GRAPH_LABEL, skip_reason=reason)
        try:
            trace = await asyncio.wait_for(
                self.search_trace(query, settings),
                settings.retrieval_timeout_ms / 1000.0,
            )
        except TimeoutError:
            return SupplementalResult(GRAPH_LABEL, skip_reason="timeout")
        except GraphBackendUnavailableError:
            return SupplementalResult(GRAPH_LABEL, skip_reason="backend_unavailable")
        except Exception as e:  # noqa: BLE001 — 답변 경로를 깨지 않는다(FR-14)
            self._logger.warning(
                "graph retrieval failed", exception=e, request_id=query.request_id
            )
            return SupplementalResult(GRAPH_LABEL, skip_reason="error")
        if trace.skip_reason is not None:
            return SupplementalResult(GRAPH_LABEL, skip_reason=trace.skip_reason)
        self._logger.info(
            "graph retrieval done",
            request_id=query.request_id,
            hits=len(trace.hits),
            seeds=len(trace.linked),
            scope=",".join(trace.scope.topic_names) or None,
            scope_by=trace.scope.decided_by,
            timings_ms=trace.timings_ms,
        )
        return SupplementalResult(
            GRAPH_LABEL, hits=trace.hits, weight=settings.graph_rrf_weight
        )

    async def search_trace(
        self,
        query: SupplementalQuery,
        settings: GraphRagSettings,
        *,
        max_hops: int | None = None,
    ) -> GraphSearchTrace:
        """검색 전 과정을 기록하며 실행(관리자 검색 테스트도 이 함수를 쓴다)."""
        trace = GraphSearchTrace()
        clock = _Clock(trace)
        # 주제 판정(LLM 이면 수 초)과 씨앗 연결을 동시에 — 범위는 근거 청크에서 건다.
        trace.scope, candidates = await asyncio.gather(
            self._route(query, settings), self._link(query)
        )
        clock.lap("route_link")
        if not candidates:
            trace.skip_reason = "no_entity"
            return trace

        # ① 범위 안 후보를 씨앗으로 우선. 하나도 없으면 범위를 풀고 진행한다.
        in_scope: set[str] | None = None
        if trace.scope.topic_ids is not None:
            in_scope = await self._store.entities_in_scope(
                [c.id for c in candidates], trace.scope.topic_ids
            )
            if not in_scope:
                trace.scope = QueryScope(reason="no_entity_in_scope")
        trace.linked = RetrievalPolicy.pick_seeds(candidates, in_scope, MAX_SEEDS)

        hops = RetrievalPolicy.hops(max_hops or settings.max_hops)
        scores = await self._traverse(trace, hops)
        allowed = set(scores)
        if trace.scope.topic_ids is not None:
            allowed = await self._store.chunks_in_scope(
                list(scores), trace.scope.topic_ids
            )
            if not allowed:  # 범위 안 근거가 없으면 범위 없이(FR-29: 놓치지 않기)
                trace.scope = QueryScope(reason="no_chunk_in_scope")
                scores = await self._traverse(trace, hops)
                allowed = set(scores)
        trace.chunk_scores = RetrievalPolicy.ranked(
            {c: s for c, s in scores.items() if c in allowed}
        )
        clock.lap("traverse")

        fetched = await self._fetcher.fetch(
            [c for c, _ in trace.chunk_scores],
            hard_filter=dict(query.hard_filter),
            lenient_filter=dict(query.lenient_filter),
            collection_name=query.collection_name,
            es_index=query.es_index,
            request_id=query.request_id,
        )
        by_id = {h.id: h for h in fetched}
        ordered = [
            replace(by_id[c], score=round(s, 4))
            for c, s in trace.chunk_scores
            if c in by_id
        ]
        trace.filtered_out = len(trace.chunk_scores) - len(ordered)
        trace.hits = ordered[: query.top_k]
        clock.lap("fetch")
        return trace

    async def _traverse(self, trace: GraphSearchTrace, hops: int) -> dict[str, float]:
        """씨앗 언급 청크 + 경로 근거 청크 점수. ② 범위가 있으면 범위 안 관계만 탄다."""
        seed_ids = [e.id for e in trace.linked]
        mentions, trace.paths = await asyncio.gather(
            self._store.seed_mentions(seed_ids, None),
            self._store.find_paths(
                seed_ids,
                hops,
                HUB_DEGREE_LIMIT,
                MAX_PATHS,
                topic_ids=trace.scope.topic_ids,
            ),
        )
        return RetrievalPolicy.chunk_scores(mentions, trace.paths)

    async def _route(
        self, query: SupplementalQuery, settings: GraphRagSettings
    ) -> QueryScope:
        budget = settings.retrieval_timeout_ms / 1000.0 * _ROUTE_BUDGET_SHARE
        try:
            return await asyncio.wait_for(
                self._router.route(query.query, settings, query.request_id), budget
            )
        except TimeoutError:
            return QueryScope(reason="route_timeout")
        except Exception as e:  # noqa: BLE001 — 범위 없이 검색
            self._logger.warning(
                "query topic routing failed", exception=e, request_id=query.request_id
            )
            return QueryScope(reason="route_error")

    async def _link(self, query: SupplementalQuery):
        phrases = RetrievalPolicy.phrases(self._morph.extract_nouns(query.query))
        embedding = None
        try:
            embedding = (await self._embedder.embed([query.query]))[0]
        except Exception as e:  # noqa: BLE001 — 벡터 없이 정확·별칭 일치만
            self._logger.warning(
                "graph query embedding failed", exception=e, request_id=query.request_id
            )
        return await self._store.link_entities(
            GLOBAL_SCOPE, phrases, embedding, None, LINK_CANDIDATES
        )


class _Clock:
    def __init__(self, trace: GraphSearchTrace) -> None:
        self._trace = trace
        self._last = time.perf_counter()

    def lap(self, name: str) -> None:
        now = time.perf_counter()
        self._trace.timings_ms[name] = int((now - self._last) * 1000)
        self._last = now
