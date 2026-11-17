"""QueryTopicRouter — 질문이 어느 주제 문서를 찾는지 고른다(검색 범위).

Design Ref: graph-rag-foundation §11.9 질문 주제, Plan FR-29 (사용자 결정):
  Jev ChoiceQuestion{대분류 주제…, NEW} → 상한 이상이면 그 주제.
  Jev 불가·실패·확신 부족 → LLM 선택(high·medium 이면 그 주제).
  그 외(NEW·low·오류·주제 없음) → 범위를 좁히지 않는다. 새 주제는 만들지 않는다.
같은 질문(공백 정규화)은 TTL 캐시로 다시 판정하지 않는다.
"""

from __future__ import annotations

import time
from dataclasses import replace

from src.application.graph_rag.resolution.resolver import (
    MAX_CONSECUTIVE_JEV_FAILURES,
)
from src.domain.graph_rag.extraction import Mention, NameNormalizer
from src.domain.graph_rag.interfaces import EntityChooserPort, TopicRepositoryPort
from src.domain.graph_rag.resolution import (
    Candidate,
    LlmConfidence,
    ResolutionPolicy,
    candidate_labels,
)
from src.domain.graph_rag.retrieval import QueryScope
from src.domain.graph_rag.topic import MAX_TOPIC_CANDIDATES, Topic, TopicLevel
from src.domain.graph_rag.value_objects import GraphRagSettings
from src.domain.logging.interfaces.logger_interface import LoggerInterface

QUERY_MENTION_TYPE = "질문"
QUERY_CHUNK_ID = "__query__"
CACHE_TTL_SECONDS = 600.0
CACHE_MAX_ENTRIES = 1000
_ACCEPTED_LLM = {LlmConfidence.HIGH, LlmConfidence.MEDIUM}


class QueryTopicRouter:
    def __init__(
        self,
        *,
        topics: TopicRepositoryPort,
        jev_chooser: EntityChooserPort | None,
        llm_chooser: EntityChooserPort,
        logger: LoggerInterface,
    ) -> None:
        self._topics = topics
        self._jev = jev_chooser
        self._llm = llm_chooser
        self._logger = logger
        self._cache: dict[str, tuple[float, QueryScope]] = {}
        self._jev_failures = 0

    async def route(
        self, query: str, settings: GraphRagSettings, request_id: str
    ) -> QueryScope:
        key = NameNormalizer.normalize(query)
        cached = self._cache.get(key)
        if cached and cached[0] > time.monotonic():
            return replace(cached[1], decided_by="cache")
        scope = await self._decide(query, settings, request_id)
        if scope.reason not in ("jev_error", "llm_error"):  # 실패는 캐시하지 않는다
            self._remember(key, scope)
        return scope

    def _remember(self, key: str, scope: QueryScope) -> None:
        if len(self._cache) >= CACHE_MAX_ENTRIES:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = (time.monotonic() + CACHE_TTL_SECONDS, scope)

    async def _decide(
        self, query: str, settings: GraphRagSettings, request_id: str
    ) -> QueryScope:
        majors = [
            t
            for t in await self._topics.list(
                request_id, level=TopicLevel.MAJOR, parent_id=None
            )
            if t.usable
        ][:MAX_TOPIC_CANDIDATES]
        if not majors:
            return QueryScope(reason="no_topics")
        labels = candidate_labels([_candidate(t) for t in majors])
        by_id = {t.id: t for t in majors}
        mention = Mention(query[:500], QUERY_MENTION_TYPE, "", QUERY_CHUNK_ID)
        reason = "jev_unavailable"
        if self._jev_usable(settings):
            try:
                verdict = await self._jev.choose(  # type: ignore[union-attr]
                    mention, query, labels, request_id
                )
                self._jev_failures = 0
                label, p = ResolutionPolicy.best_candidate(verdict.probabilities or {})
                if label in labels and p >= settings.link_threshold:
                    return _scope(by_id[labels[label].entity_id], "jev")
                reason = "jev_unsure"
            except Exception as e:  # noqa: BLE001 — Jev 실패는 LLM 으로
                self._jev_failures += 1
                reason = "jev_error"
                self._logger.warning(
                    "jev query topic failed — llm fallback",
                    exception=e,
                    request_id=request_id,
                )
        try:
            verdict = await self._llm.choose(mention, query, labels, request_id)
        except Exception as e:  # noqa: BLE001 — 범위 없이 검색
            self._logger.warning(
                "llm query topic failed — no scope",
                exception=e,
                request_id=request_id,
                after=reason,
            )
            return QueryScope(reason="llm_error")
        if verdict.label not in labels:
            return QueryScope(reason="no_matching_topic")
        if verdict.confidence not in _ACCEPTED_LLM:
            return QueryScope(reason="llm_unsure")
        return _scope(by_id[labels[verdict.label].entity_id], "llm")

    def _jev_usable(self, settings: GraphRagSettings) -> bool:
        return (
            self._jev is not None
            and settings.jev_enabled
            and self._jev_failures < MAX_CONSECUTIVE_JEV_FAILURES
        )


def _scope(topic: Topic, decided_by: str) -> QueryScope:
    # 문서 대표 연결에는 대분류가 항상 있으므로 대분류 id 하나로 범위를 정한다.
    return QueryScope(
        topic_ids=(topic.id,), topic_names=(topic.name,), decided_by=decided_by
    )


def _candidate(t: Topic) -> Candidate:
    return Candidate(
        entity_id=t.id,
        name=t.name,
        type="주제",
        description=t.description or "",
        aliases=(),
        match="topic",
        similarity=1.0,
    )
