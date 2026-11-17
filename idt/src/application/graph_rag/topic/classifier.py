"""DocumentTopicClassifier — 문서 주제를 자동으로 분류한다.

Design Ref: graph-rag-foundation §11.9 (module-4b), Plan FR-25~28.
흐름(잡마다 1회):
  문서 앞부분 → LLM 주제 제안(대분류·소분류·보조)
  대분류 판정 → 그 대분류 아래 소분류 판정 (엔티티 판정과 같은 규칙)
    정확 일치 → 연결(rule) / 후보 0 → 새 주제(rule, 검토 대기)
    Jev 사용 가능 → 세 구간(연결 / 새로 / LLM 재판정·검토 대기)
    Jev 불가 → LLM 선택(확신도 high 아니면 검토 대기), LLM 실패 → 새 주제(검토 대기)
  보조 대분류(최대 2) → 기존 주제에만 연결. 정확 일치 또는 Jev 연결 구간만 쓴다
  자동으로 만든 주제는 status=pending, 그 판정은 항상 검토 대기.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from src.application.graph_rag.resolution.resolver import (
    MAX_CONSECUTIVE_JEV_FAILURES,
    ResolveRunState,
)
from src.domain.graph_rag.exceptions import (
    GraphTopicDuplicateError,
    GraphTopicInvalidError,
)
from src.domain.graph_rag.extraction import ChunkUnit, Mention
from src.domain.graph_rag.interfaces import (
    DecisionStorePort,
    DocumentTopicStorePort,
    EntityChooserPort,
    TopicProposerPort,
    TopicRepositoryPort,
)
from src.domain.graph_rag.resolution import (
    NEW_LABEL,
    Candidate,
    ChooserVerdict,
    DecidedBy,
    LlmConfidence,
    ResolutionBand,
    ResolutionDecision,
    ResolutionPolicy,
    ReviewStatus,
    candidate_labels,
)
from src.domain.graph_rag.topic import (
    DOCUMENT_CHUNK_ID,
    MAX_SECONDARY_TOPICS,
    MAX_TOPIC_CANDIDATES,
    MAX_TOPIC_DESCRIPTION,
    DocumentTopic,
    Topic,
    TopicLevel,
    TopicOrigin,
    TopicPolicy,
    TopicStatus,
    TopicSuggestion,
    mention_type_for,
    topic_decision_id,
)
from src.domain.graph_rag.value_objects import GraphRagSettings
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_CONTEXT_CHARS = 1200


@dataclass
class TopicRunResult:
    topic_ids: list[str] = field(default_factory=list)
    decisions: list[ResolutionDecision] = field(default_factory=list)
    llm_calls: int = 0
    judge_calls: int = 0


@dataclass
class _Ctx:
    job_id: str
    document_id: str
    context: str
    settings: GraphRagSettings
    state: ResolveRunState
    request_id: str
    result: TopicRunResult


@dataclass(frozen=True)
class _Resolved:
    topic: Topic
    decision: ResolutionDecision


@dataclass(frozen=True)
class _Slot:
    level: TopicLevel
    parent_id: str | None
    suggestion: TopicSuggestion
    name: str
    key: str  # decision slot: major / minor / secondaryN
    allow_new: bool


class DocumentTopicClassifier:
    def __init__(
        self,
        *,
        topics: TopicRepositoryPort,
        document_topics: DocumentTopicStorePort,
        decisions: DecisionStorePort,
        proposer: TopicProposerPort,
        llm_chooser: EntityChooserPort,
        jev_chooser: EntityChooserPort | None,
        logger: LoggerInterface,
    ) -> None:
        self._topics = topics
        self._links = document_topics
        self._decisions = decisions
        self._proposer = proposer
        self._llm = llm_chooser
        self._jev = jev_chooser
        self._logger = logger

    async def current(self, document_id: str, request_id: str) -> list[str]:
        """문서에 이미 연결된 주제 id (대표 먼저)."""
        links = await self._links.list_for_document(document_id, request_id)
        return [lk.topic_id for lk in sorted(links, key=lambda lk: not lk.is_primary)]

    async def classify(
        self,
        *,
        job_id: str,
        document_id: str,
        units: list[ChunkUnit],
        settings: GraphRagSettings,
        state: ResolveRunState,
        request_id: str,
    ) -> TopicRunResult:
        result = TopicRunResult()
        excerpt = TopicPolicy.excerpt(units)
        if not excerpt.strip():
            return result
        proposal = await self._proposer.propose(excerpt, request_id)
        result.llm_calls += 1
        ctx = _Ctx(
            job_id,
            document_id,
            excerpt[:_CONTEXT_CHARS],
            settings,
            state,
            request_id,
            result,
        )
        links: list[DocumentTopic] = []

        major = await self._resolve_slot(
            ctx, TopicLevel.MAJOR, None, proposal.major, "major", allow_new=True
        )
        if major is not None:
            links.append(self._link(ctx, major, primary=True))
            if proposal.minor is not None:
                minor = await self._resolve_slot(
                    ctx,
                    TopicLevel.MINOR,
                    major.topic.id,
                    proposal.minor,
                    "minor",
                    allow_new=True,
                )
                if minor is not None:
                    links.append(self._link(ctx, minor, primary=True))
            for i, name in enumerate(self._secondary_names(proposal, major.topic)):
                found = await self._resolve_slot(
                    ctx,
                    TopicLevel.MAJOR,
                    None,
                    TopicSuggestion(name),
                    f"secondary{i}",
                    allow_new=False,
                )
                if found and found.topic.id not in {lk.topic_id for lk in links}:
                    links.append(self._link(ctx, found, primary=False))

        if result.decisions:
            await self._decisions.upsert_many(result.decisions, request_id)
        await self._links.replace(document_id, links, request_id)
        result.topic_ids = [lk.topic_id for lk in links]
        return result

    @staticmethod
    def _secondary_names(proposal, major: Topic) -> list[str]:
        names: list[str] = []
        for raw in proposal.secondary:
            if TopicPolicy.normalize(raw) == major.normalized_name:
                continue
            names.append(raw)
            if len(names) == MAX_SECONDARY_TOPICS:
                break
        return names

    def _link(self, ctx: _Ctx, r: _Resolved, *, primary: bool) -> DocumentTopic:
        ctx.result.decisions.append(r.decision)
        return DocumentTopic(
            document_id=ctx.document_id,
            topic_id=r.topic.id,
            is_primary=primary,
            probability=r.decision.probability,
            decision_id=r.decision.id,
        )

    # ── 판정 ────────────────────────────────────────────────────────────────

    async def _resolve_slot(
        self,
        ctx: _Ctx,
        level: TopicLevel,
        parent_id: str | None,
        suggestion: TopicSuggestion,
        key: str,
        *,
        allow_new: bool,
    ) -> _Resolved | None:
        try:
            name = TopicPolicy.clean_name(suggestion.name)
        except GraphTopicInvalidError:
            self._logger.warning(
                "topic suggestion has invalid name — skipped",
                request_id=ctx.request_id,
                slot=key,
            )
            return None
        slot = _Slot(level, parent_id, suggestion, name, key, allow_new)
        existing = [
            t
            for t in await self._topics.list(
                ctx.request_id, level=level, parent_id=parent_id
            )
            if t.usable
        ][:MAX_TOPIC_CANDIDATES]
        norm = TopicPolicy.normalize(name)
        exact = next((t for t in existing if t.normalized_name == norm), None)
        if exact is not None:
            return self._linked(
                ctx,
                slot,
                exact,
                DecidedBy.RULE,
                ResolutionBand.AUTO_LINK,
                candidates=[exact],
            )
        if not existing:
            if not allow_new:
                return None
            return await self._new(ctx, slot, DecidedBy.RULE, ResolutionBand.AUTO_NEW)
        return await self._judge(ctx, slot, existing)

    async def _judge(self, ctx: _Ctx, slot: _Slot, existing: list[Topic]):
        labels = candidate_labels([_candidate(t, slot.level) for t in existing])
        by_id = {t.id: t for t in existing}
        mention = Mention(
            slot.name,
            mention_type_for(slot.level),
            slot.suggestion.description,
            DOCUMENT_CHUNK_ID,
        )
        if self._jev_usable(ctx):
            try:
                verdict = await self._jev.choose(  # type: ignore[union-attr]
                    mention, ctx.context, labels, ctx.request_id
                )
                ctx.state.jev_failures = 0
                ctx.result.judge_calls += 1
                return await self._from_jev(ctx, slot, mention, labels, by_id, verdict)
            except Exception as e:  # noqa: BLE001 — Jev 실패는 LLM 대체(FR-25)
                ctx.state.jev_failures += 1
                self._logger.warning(
                    "jev topic judgment failed — llm fallback",
                    exception=e,
                    request_id=ctx.request_id,
                )
        if not slot.allow_new:
            return None  # 보조 주제는 LLM 을 부르지 않는다
        return await self._from_llm(
            ctx,
            slot,
            mention,
            labels,
            by_id,
            DecidedBy.LLM_FALLBACK,
            ResolutionBand.FALLBACK,
            probability=None,
        )

    def _jev_usable(self, ctx: _Ctx) -> bool:
        return (
            self._jev is not None
            and ctx.settings.jev_enabled
            and ctx.state.jev_failures < MAX_CONSECUTIVE_JEV_FAILURES
        )

    async def _from_jev(self, ctx, slot, mention, labels, by_id, verdict):
        probs = verdict.probabilities or {}
        label, p = ResolutionPolicy.best_candidate(probs)
        band = ResolutionPolicy.classify(
            p,
            link_threshold=ctx.settings.link_threshold,
            new_threshold=ctx.settings.new_threshold,
        )
        common = dict(
            candidates=[by_id[c.entity_id] for c in labels.values()],
            probabilities=probs,
            probability=p,
        )
        if band is ResolutionBand.AUTO_LINK:
            topic = by_id[labels[label].entity_id]
            return self._linked(
                ctx, slot, topic, DecidedBy.JEV, band, label=label, **common
            )
        if not slot.allow_new:
            return None
        if band is ResolutionBand.AUTO_NEW:
            return await self._new(ctx, slot, DecidedBy.JEV, band, **common)
        return await self._from_llm(
            ctx,
            slot,
            mention,
            labels,
            by_id,
            DecidedBy.LLM_REJUDGE,
            ResolutionBand.REJUDGE,
            probability=p,
            probabilities=probs,
            force_review=True,
        )

    async def _from_llm(
        self,
        ctx,
        slot,
        mention,
        labels,
        by_id,
        decided_by,
        band,
        *,
        probability,
        probabilities=None,
        force_review=False,
    ):
        common = dict(
            candidates=[by_id[c.entity_id] for c in labels.values()],
            probabilities=probabilities,
            probability=probability,
        )
        ctx.result.llm_calls += 1
        try:
            verdict: ChooserVerdict = await self._llm.choose(
                mention, ctx.context, labels, ctx.request_id
            )
        except Exception as e:  # noqa: BLE001 — 실패하면 새 주제 + 검토 대기
            self._logger.warning(
                "llm topic judgment failed — created new",
                exception=e,
                request_id=ctx.request_id,
            )
            return await self._new(
                ctx, slot, decided_by, band, reason="llm error", **common
            )
        review = (
            ReviewStatus.PENDING
            if force_review or verdict.confidence is not LlmConfidence.HIGH
            else ReviewStatus.NONE
        )
        extra = dict(confidence=verdict.confidence, reason=verdict.reason, **common)
        if verdict.label in labels:
            topic = by_id[labels[verdict.label].entity_id]
            return self._linked(
                ctx,
                slot,
                topic,
                decided_by,
                band,
                label=verdict.label,
                review=review,
                **extra,
            )
        return await self._new(ctx, slot, decided_by, band, **extra)

    # ── 결과 ────────────────────────────────────────────────────────────────

    def _linked(
        self,
        ctx,
        slot,
        topic,
        decided_by,
        band,
        *,
        label=None,
        review=ReviewStatus.NONE,
        candidates=(),
        **kw,
    ) -> _Resolved:
        if label is None:
            label = next(
                (
                    k
                    for k, c in candidate_labels(
                        [_candidate(t, slot.level) for t in candidates]
                    ).items()
                    if c.entity_id == topic.id
                ),
                NEW_LABEL,
            )
        decision = _decision(
            ctx,
            slot,
            topic.id,
            False,
            decided_by,
            band,
            candidates=candidates,
            label=label,
            review=review,
            **kw,
        )
        return _Resolved(topic, decision)

    async def _new(self, ctx, slot, decided_by, band, *, candidates=(), **kw):
        topic = Topic(
            id=str(uuid.uuid4()),
            name=slot.name,
            normalized_name=TopicPolicy.normalize(slot.name),
            level=slot.level,
            parent_id=slot.parent_id,
            description=(slot.suggestion.description or "")[:MAX_TOPIC_DESCRIPTION],
            status=TopicStatus.PENDING,
            origin=TopicOrigin.AUTO,
        )
        try:
            topic = await self._topics.create(topic, ctx.request_id)
        except GraphTopicDuplicateError:
            # 정규화 이름이 같은 retired 주제 — 되살려 검토 대기로 둔다
            found = await self._topics.find_by_name(
                topic.parent_key, topic.normalized_name, ctx.request_id
            )
            if found is None:
                raise
            topic = await self._topics.update(_revive(found), ctx.request_id)
        kw.pop("review", None)
        decision = _decision(
            ctx,
            slot,
            topic.id,
            True,
            decided_by,
            band,
            candidates=candidates,
            label=NEW_LABEL,
            review=ReviewStatus.PENDING,
            **kw,
        )
        return _Resolved(topic, decision)


def _revive(t: Topic) -> Topic:
    from dataclasses import replace

    return replace(t, status=TopicStatus.PENDING)


def _candidate(t: Topic, level: TopicLevel) -> Candidate:
    return Candidate(
        entity_id=t.id,
        name=t.name,
        type=mention_type_for(level),
        description=t.description or "",
        aliases=(),
        match="topic",
        similarity=1.0,
    )


def _decision(
    ctx: _Ctx,
    slot: _Slot,
    topic_id: str,
    created_new: bool,
    decided_by: DecidedBy,
    band: ResolutionBand,
    *,
    candidates=(),
    probabilities=None,
    probability=None,
    label=NEW_LABEL,
    review=ReviewStatus.NONE,
    confidence=None,
    reason=None,
) -> ResolutionDecision:
    labeled = candidate_labels([_candidate(t, slot.level) for t in candidates])
    return ResolutionDecision(
        id=topic_decision_id(ctx.document_id, slot.key),
        job_id=ctx.job_id,
        document_id=ctx.document_id,
        chunk_id=DOCUMENT_CHUNK_ID,
        mention_text=slot.name[:255],
        mention_type=mention_type_for(slot.level),
        candidates=tuple(
            {
                "label": k,
                "entity_id": c.entity_id,
                "name": c.name,
                "type": c.type,
                "match": c.match,
                "similarity": 1.0,
            }
            for k, c in labeled.items()
        ),
        probabilities=probabilities,
        chosen_label=label,
        entity_id=topic_id,
        created_new=created_new,
        decided_by=decided_by,
        band=band,
        probability=probability,
        llm_confidence=confidence,
        llm_reason=(reason or None) and reason[:500],
        review_status=review,
    )
