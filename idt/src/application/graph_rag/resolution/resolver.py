"""EntityResolver — 언급 하나가 기존 엔티티와 같은 대상인지 판정한다.

Design Ref: graph-rag-foundation §2.2(판정)·§6.2, Plan FR-08~10.
흐름(언급마다):
  값 이름 → 청크 단위 새 엔티티(판정 없음, M3-12)
  같은 잡에서 이미 만든 엔티티 → 연결(rule)
  후보 검색(정규화 이름·별칭 정확 일치 + 이름 벡터 top-K, 타입 호환만)
    후보 0 → 새 엔티티(rule)
    같은 타입 정확 일치 1개 → 연결(rule)
    Jev 사용 가능 → ChoiceQuestion 확률로 세 구간(연결 / 새로 / LLM 재판정·검토 대기)
    Jev 불가(설정 off·미조립·오류) → LLM 선택(확신도 high 아니면 검토 대기)
  LLM 실패 → 새 엔티티 + 검토 대기(잘못 합치기보다 쪼개지는 쪽을 택한다)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from src.domain.graph_rag.extraction import (
    GLOBAL_SCOPE,
    AliasWrite,
    ChunkUnit,
    EntityWrite,
    LiteralValuePolicy,
    Mention,
    NameNormalizer,
    decision_id_for,
)
from src.domain.graph_rag.interfaces import (
    EntityChooserPort,
    EntityEmbedderPort,
    GraphStorePort,
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
    types_compatible,
)
from src.domain.graph_rag.value_objects import OTHER_TYPE, GraphRagSettings
from src.domain.logging.interfaces.logger_interface import LoggerInterface

MAX_CONSECUTIVE_JEV_FAILURES = 5
_CONTEXT_PAD = 300


@dataclass
class ResolveRunState:
    """잡 하나 동안 유지하는 판정 상태."""

    known: dict[tuple[str, str], str] = field(default_factory=dict)  # (키,타입)→id
    jev_failures: int = 0


@dataclass
class ResolveOutcome:
    lookup_key: str
    entity_id: str
    decision: ResolutionDecision
    new_entity: EntityWrite | None = None
    alias: AliasWrite | None = None
    judge_calls: int = 0
    llm_calls: int = 0


@dataclass
class _Ctx:
    unit: ChunkUnit
    job_id: str
    settings: GraphRagSettings
    state: ResolveRunState
    request_id: str


def _context(text: str, name: str) -> str:
    pos = text.find(name)
    if pos < 0:
        return text[: _CONTEXT_PAD * 2]
    return text[max(0, pos - _CONTEXT_PAD) : pos + len(name) + _CONTEXT_PAD]


class EntityResolver:
    def __init__(
        self,
        *,
        store: GraphStorePort,
        embedder: EntityEmbedderPort,
        llm_chooser: EntityChooserPort,
        jev_chooser: EntityChooserPort | None,
        logger: LoggerInterface,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._llm = llm_chooser
        self._jev = jev_chooser
        self._logger = logger

    async def resolve_chunk(
        self,
        mentions: tuple[Mention, ...] | list[Mention],
        unit: ChunkUnit,
        *,
        job_id: str,
        settings: GraphRagSettings,
        state: ResolveRunState,
        request_id: str,
    ) -> list[ResolveOutcome]:
        ctx = _Ctx(unit, job_id, settings, state, request_id)
        unique = self._unique(mentions)
        searchable = [
            m
            for m in unique
            if m.key is None and not LiteralValuePolicy.is_literal(m.name)
        ]
        vectors = await self._embed([m.name for m in searchable], request_id)
        by_name = dict(zip([m.name for m in searchable], vectors, strict=True))
        outcomes = []
        for m in unique:
            outcomes.append(await self._resolve_one(m, by_name.get(m.name), ctx))
        return outcomes

    @staticmethod
    def _unique(mentions) -> list[Mention]:
        seen, out = set(), []
        for m in mentions:
            if m.lookup_key and m.lookup_key not in seen:
                seen.add(m.lookup_key)
                out.append(m)
        return out

    async def _embed(
        self, names: list[str], request_id: str
    ) -> list[list[float] | None]:
        if not names:
            return []
        try:
            return list(await self._embedder.embed(names))
        except Exception as e:  # noqa: BLE001 — 벡터 없이 정확 일치만으로 판정
            self._logger.warning(
                "entity name embedding failed",
                exception=e,
                request_id=request_id,
                count=len(names),
            )
            return [None] * len(names)

    def _type(self, m: Mention, settings: GraphRagSettings) -> str:
        t = (m.type or "").strip()
        return t if t in settings.entity_types else OTHER_TYPE

    async def _resolve_one(
        self, m: Mention, vector: list[float] | None, ctx: _Ctx
    ) -> ResolveOutcome:
        type_ = self._type(m, ctx.settings)
        literal = m.key is None and LiteralValuePolicy.is_literal(m.name)
        store_key = f"{m.chunk_id}::{m.lookup_key}" if literal else m.lookup_key
        known = ctx.state.known.get((store_key, type_))
        if known:
            return self._outcome(
                m, type_, ctx, known, DecidedBy.RULE, ResolutionBand.AUTO_LINK
            )
        if literal or m.key is not None:
            return self._new(
                m, type_, store_key, None, ctx, DecidedBy.RULE, ResolutionBand.AUTO_NEW
            )
        candidates = [
            c
            for c in await self._store.find_candidates(
                GLOBAL_SCOPE, store_key, vector, ctx.settings.candidate_top_k
            )
            if types_compatible(c.type, type_)
        ]
        if not candidates:
            return self._new(
                m,
                type_,
                store_key,
                vector,
                ctx,
                DecidedBy.RULE,
                ResolutionBand.AUTO_NEW,
            )
        exact = ResolutionPolicy.unambiguous_exact(candidates, type_)
        if exact is not None:
            return self._outcome(
                m,
                type_,
                ctx,
                exact.entity_id,
                DecidedBy.RULE,
                ResolutionBand.AUTO_LINK,
                candidates=candidates,
                linked=exact,
            )
        return await self._judge(m, type_, store_key, vector, candidates, ctx)

    async def _judge(
        self, m: Mention, type_: str, store_key: str, vector, candidates, ctx: _Ctx
    ) -> ResolveOutcome:
        labels = candidate_labels(candidates)
        context = _context(ctx.unit.content, m.name)
        if self._jev_usable(ctx):
            try:
                verdict = await self._jev.choose(m, context, labels, ctx.request_id)  # type: ignore[union-attr]
                ctx.state.jev_failures = 0
                return await self._from_jev(
                    m, type_, store_key, vector, labels, verdict, context, ctx
                )
            except Exception as e:  # noqa: BLE001 — Jev 실패는 LLM 대체(FR-09)
                ctx.state.jev_failures += 1
                self._logger.warning(
                    "jev entity judgment failed — llm fallback",
                    exception=e,
                    request_id=ctx.request_id,
                )
        outcome = await self._from_llm(
            m,
            type_,
            store_key,
            vector,
            labels,
            context,
            ctx,
            DecidedBy.LLM_FALLBACK,
            ResolutionBand.FALLBACK,
            probability=None,
        )
        return outcome

    def _jev_usable(self, ctx: _Ctx) -> bool:
        return (
            self._jev is not None
            and ctx.settings.jev_enabled
            and ctx.state.jev_failures < MAX_CONSECUTIVE_JEV_FAILURES
        )

    async def _from_jev(
        self,
        m,
        type_,
        store_key,
        vector,
        labels,
        verdict: ChooserVerdict,
        context,
        ctx: _Ctx,
    ) -> ResolveOutcome:
        probs = verdict.probabilities or {}
        label, p = ResolutionPolicy.best_candidate(probs)
        band = ResolutionPolicy.classify(
            p,
            link_threshold=ctx.settings.link_threshold,
            new_threshold=ctx.settings.new_threshold,
        )
        if band is ResolutionBand.REJUDGE:
            out = await self._from_llm(
                m,
                type_,
                store_key,
                vector,
                labels,
                context,
                ctx,
                DecidedBy.LLM_REJUDGE,
                ResolutionBand.REJUDGE,
                probability=p,
                probabilities=probs,
                force_review=True,
            )
            out.judge_calls = 1
            return out
        common = dict(
            candidates=list(labels.values()),
            probabilities=probs,
            probability=p,
            judge_calls=1,
        )
        if band is ResolutionBand.AUTO_LINK:
            return self._outcome(
                m,
                type_,
                ctx,
                labels[label].entity_id,
                DecidedBy.JEV,
                band,
                linked=labels[label],
                label=label,
                **common,
            )
        return self._new(
            m, type_, store_key, vector, ctx, DecidedBy.JEV, band, **common
        )

    async def _from_llm(
        self,
        m,
        type_,
        store_key,
        vector,
        labels,
        context,
        ctx: _Ctx,
        decided_by: DecidedBy,
        band: ResolutionBand,
        *,
        probability: float | None,
        probabilities: dict | None = None,
        force_review: bool = False,
    ) -> ResolveOutcome:
        common = dict(
            candidates=list(labels.values()),
            probabilities=probabilities,
            probability=probability,
        )
        try:
            verdict = await self._llm.choose(m, context, labels, ctx.request_id)
        except Exception as e:  # noqa: BLE001 — 실패하면 새 엔티티 + 검토 대기
            self._logger.warning(
                "llm entity judgment failed — created new",
                exception=e,
                request_id=ctx.request_id,
            )
            out = self._new(
                m,
                type_,
                store_key,
                vector,
                ctx,
                decided_by,
                band,
                review=ReviewStatus.PENDING,
                reason="llm error",
                **common,
            )
            out.llm_calls = 1
            return out
        review = (
            ReviewStatus.PENDING
            if (force_review or verdict.confidence is not LlmConfidence.HIGH)
            else ReviewStatus.NONE
        )
        extra = dict(
            review=review,
            confidence=verdict.confidence,
            reason=verdict.reason,
            **common,
        )
        if verdict.label in labels:
            out = self._outcome(
                m,
                type_,
                ctx,
                labels[verdict.label].entity_id,
                decided_by,
                band,
                linked=labels[verdict.label],
                label=verdict.label,
                **extra,
            )
        else:
            out = self._new(m, type_, store_key, vector, ctx, decided_by, band, **extra)
        out.llm_calls = 1
        return out

    def _decision(
        self,
        m: Mention,
        type_: str,
        ctx: _Ctx,
        entity_id: str,
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
        labeled = candidate_labels(list(candidates))
        return ResolutionDecision(
            id=decision_id_for(m.chunk_id, m.lookup_key, type_),
            job_id=ctx.job_id,
            document_id=ctx.unit.document_id,
            chunk_id=m.chunk_id,
            mention_text=m.name[:255],
            mention_type=type_,
            candidates=tuple(
                {
                    "label": k,
                    "entity_id": c.entity_id,
                    "name": c.name,
                    "type": c.type,
                    "match": c.match,
                    "similarity": round(c.similarity, 4),
                }
                for k, c in labeled.items()
            ),
            probabilities=probabilities,
            chosen_label=label,
            entity_id=entity_id,
            created_new=created_new,
            decided_by=decided_by,
            band=band,
            probability=probability,
            llm_confidence=confidence,
            llm_reason=(reason or None) and reason[:500],
            review_status=review,
        )

    def _outcome(
        self,
        m,
        type_,
        ctx: _Ctx,
        entity_id: str,
        decided_by,
        band,
        *,
        linked: Candidate | None = None,
        judge_calls: int = 0,
        **kw,
    ) -> ResolveOutcome:
        alias = None
        if linked is not None and NameNormalizer.normalize(linked.name) != m.lookup_key:
            alias = AliasWrite(entity_id, GLOBAL_SCOPE, m.lookup_key, m.name)
        return ResolveOutcome(
            lookup_key=m.lookup_key,
            entity_id=entity_id,
            decision=self._decision(
                m, type_, ctx, entity_id, False, decided_by, band, **kw
            ),
            alias=alias,
            judge_calls=judge_calls,
        )

    def _new(
        self,
        m,
        type_,
        store_key,
        vector,
        ctx: _Ctx,
        decided_by,
        band,
        *,
        judge_calls: int = 0,
        **kw,
    ) -> ResolveOutcome:
        entity = EntityWrite(
            id=str(uuid.uuid4()),
            scope_key=GLOBAL_SCOPE,
            name=m.name,
            normalized_name=store_key,
            type=type_,
            description=m.description,
            name_embedding=tuple(vector) if vector else None,
        )
        ctx.state.known[(store_key, type_)] = entity.id
        return ResolveOutcome(
            lookup_key=m.lookup_key,
            entity_id=entity.id,
            decision=self._decision(
                m, type_, ctx, entity.id, True, decided_by, band, **kw
            ),
            new_entity=entity,
            judge_calls=judge_calls,
        )
