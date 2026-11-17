"""ExtractGraphUseCase — 문서 1건의 그래프 추출 잡 실행.

Design Ref: graph-rag-foundation §2.2(적재)·§3.4·§6.2, Plan FR-04~07·FR-18.
- LLM 추출은 동시 실행(설정 concurrency), 판정·쓰기는 잠금으로 직렬화한다
  (같은 새 엔티티를 두 청크가 동시에 만드는 경합 방지).
- 청크 실패는 세고 계속 진행한다. 호출 상한에 닿으면 남은 청크는 건너뛰고 partial.
- 판정은 EntityResolver(module-4: 후보 검색 + Jev 세 구간 + LLM 재판정·대체).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from src.application.graph_rag.resolution.resolver import (
    EntityResolver,
    ResolveRunState,
)
from src.domain.graph_rag.exceptions import GraphBackendUnavailableError
from src.domain.graph_rag.extraction import (
    EXTRACTOR_VERSION,
    ChunkGraphWrite,
    ChunkUnit,
    EvidencePolicy,
    ExtractionContext,
    ExtractionJob,
    ExtractionResult,
    JobCounters,
    JobMode,
    JobStatus,
    MentionWrite,
    NameNormalizer,
    RelationDraft,
    RelationWrite,
    relation_id_for,
)
from src.domain.graph_rag.interfaces import (
    ChunkSourcePort,
    DecisionStorePort,
    ExtractionJobStorePort,
    GraphExtractorPort,
    GraphSettingsReaderPort,
    GraphStorePort,
)
from src.domain.graph_rag.value_objects import (
    OTHER_TYPE,
    GraphRagSettings,
    RolloutStage,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_BUDGET_MSG = "llm call budget exhausted (max_llm_calls_per_doc)"


@dataclass
class _RunState:
    settings: GraphRagSettings
    context: ExtractionContext
    counters: JobCounters
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    resolve: ResolveRunState = field(default_factory=ResolveRunState)
    budget_hit: bool = False


class ExtractGraphUseCase:
    def __init__(
        self,
        *,
        jobs: ExtractionJobStorePort,
        chunks: ChunkSourcePort,
        rule_extractor: GraphExtractorPort,
        llm_extractor: GraphExtractorPort,
        store: GraphStorePort | None,
        reader: GraphSettingsReaderPort,
        resolver: EntityResolver,
        decisions: DecisionStorePort,
        logger: LoggerInterface,
    ) -> None:
        self._jobs = jobs
        self._chunks = chunks
        self._rules = rule_extractor
        self._llm = llm_extractor
        self._store = store
        self._reader = reader
        self._resolver = resolver
        self._decisions = decisions
        self._logger = logger

    async def run(self, job_id: str, request_id: str) -> None:
        job = await self._jobs.get(job_id, request_id)
        if job is None:
            return
        settings = await self._reader.get()
        problem = self._precondition(settings)
        if problem:
            await self._jobs.finish(
                job_id, JobStatus.FAILED, JobCounters(), problem, request_id
            )
            return
        try:
            await self._execute(job, settings, request_id)
        except Exception as e:  # noqa: BLE001 — 잡 실패는 기록하고 삼킨다
            self._logger.error(
                "graph extraction job failed",
                exception=e,
                request_id=request_id,
                job_id=job_id,
            )
            await self._jobs.finish(
                job_id,
                JobStatus.FAILED,
                JobCounters(),
                f"{type(e).__name__}: {e}"[:500],
                request_id,
            )

    def _precondition(self, s: GraphRagSettings) -> str | None:
        if s.rollout_stage is RolloutStage.OFF:
            return "stage_off"
        if not s.extraction_llm_model_id:
            return "extraction model not configured"
        if self._store is None:
            return "graph backend unavailable"
        return None

    async def _execute(
        self, job: ExtractionJob, settings: GraphRagSettings, request_id: str
    ) -> None:
        units = await self._chunks.list_units(job.document_id, request_id)
        if job.mode is JobMode.REBUILD:
            await self._store.delete_document(job.document_id)  # type: ignore[union-attr]
            done: set[str] = set()
        else:
            done = await self._store.extracted_chunk_ids(  # type: ignore[union-attr]
                job.document_id, EXTRACTOR_VERSION
            )
        todo = [u for u in units if u.chunk_id not in done]
        await self._jobs.mark_processing(job.id, len(units), request_id)
        state = _RunState(
            settings=settings,
            context=ExtractionContext(
                model_id=settings.extraction_llm_model_id or "",
                entity_types=settings.entity_types,
                relation_types=settings.relation_types,
                request_id=request_id,
            ),
            counters=JobCounters(processed_chunks=len(units) - len(todo)),
        )
        semaphore = asyncio.Semaphore(settings.concurrency)
        await asyncio.gather(
            *(self._process(job.id, u, state, semaphore, request_id) for u in todo)
        )
        status, error = self._final_status(state, len(todo))
        await self._jobs.finish(job.id, status, state.counters, error, request_id)

    @staticmethod
    def _final_status(state: _RunState, todo: int) -> tuple[JobStatus, str | None]:
        c = state.counters
        if todo and c.failed_chunks == todo:
            return JobStatus.FAILED, "all chunks failed"
        if state.budget_hit:
            return JobStatus.PARTIAL, _BUDGET_MSG
        if c.failed_chunks:
            return JobStatus.PARTIAL, f"{c.failed_chunks} chunks failed"
        return JobStatus.COMPLETED, None

    async def _process(
        self,
        job_id: str,
        unit: ChunkUnit,
        state: _RunState,
        semaphore: asyncio.Semaphore,
        request_id: str,
    ) -> None:
        async with semaphore:
            if state.counters.llm_calls >= state.settings.max_llm_calls_per_doc:
                state.budget_hit = True
                return
            try:
                result = await self._extract(unit, state)
            except Exception as e:  # noqa: BLE001 — 청크 단위 격리
                self._chunk_failed(state, unit, e, request_id)
                return
        async with state.lock:
            try:
                await self._write(job_id, unit, result, state)
            except Exception as e:  # noqa: BLE001
                self._chunk_failed(state, unit, e, request_id)
                return
            state.counters.processed_chunks += 1
            await self._jobs.save_progress(job_id, state.counters, request_id)

    def _chunk_failed(
        self, state: _RunState, unit: ChunkUnit, e: Exception, request_id: str
    ) -> None:
        state.counters.failed_chunks += 1
        level = self._logger.warning
        if not isinstance(e, GraphBackendUnavailableError):
            level = self._logger.error
        level(
            "graph extraction chunk failed",
            exception=e,
            request_id=request_id,
            chunk_id=unit.chunk_id,
        )

    async def _extract(self, unit: ChunkUnit, state: _RunState) -> ExtractionResult:
        rules = await self._rules.extract(unit, state.context)
        state.counters.llm_calls += 1  # 상한 판단은 호출 전에 예약해 둔다
        llm = await self._llm.extract(unit, state.context)
        state.counters.llm_calls += llm.llm_calls - 1
        # LLM 언급을 먼저 판정한다 — 규칙이 만든 조문 제목 개념과 이름이 같으면
        # LLM 이 붙인 타입을 따른다(규칙 언급은 LLM 이 놓친 경우만 채운다).
        return ExtractionResult(
            mentions=llm.mentions + rules.mentions,
            relations=rules.relations + llm.relations,
            llm_calls=llm.llm_calls,
        )

    async def _write(
        self, job_id: str, unit: ChunkUnit, result: ExtractionResult, state: _RunState
    ) -> None:
        """판정(module-4 EntityResolver) → 판정 기록(MySQL) → 그래프(Neo4j) 순서.

        판정 기록을 먼저 남겨 Neo4j 쓰기가 실패해도 무엇을 판정했는지 감사할 수
        있게 한다. 재실행 시 같은 decision_id(uuid5)로 덮어쓴다(Design §3.4).
        """
        outcomes = await self._resolver.resolve_chunk(
            result.mentions,
            unit,
            job_id=job_id,
            settings=state.settings,
            state=state.resolve,
            request_id=state.context.request_id,
        )
        resolved = {o.lookup_key: (o.entity_id, o.decision.id) for o in outcomes}
        relations = self._relations(unit, result.relations, resolved, state)
        await self._decisions.upsert_many(
            [o.decision for o in outcomes], state.context.request_id
        )
        new_entities = [o.new_entity for o in outcomes if o.new_entity]
        await self._store.write_chunk_graph(  # type: ignore[union-attr]
            ChunkGraphWrite(
                unit=unit,
                extractor_version=EXTRACTOR_VERSION,
                new_entities=tuple(new_entities),
                mentions=tuple(
                    MentionWrite(eid, did) for eid, did in resolved.values()
                ),
                relations=tuple(relations),
                aliases=tuple(o.alias for o in outcomes if o.alias),
            )
        )
        c = state.counters
        c.entities_created += len(new_entities)
        c.entities_linked += len(outcomes) - len(new_entities)
        c.relations_created += len(relations)
        c.judge_calls += sum(o.judge_calls for o in outcomes)
        c.llm_calls += sum(o.llm_calls for o in outcomes)

    @staticmethod
    def _relations(
        unit: ChunkUnit,
        drafts: tuple[RelationDraft, ...],
        resolved: dict[str, tuple[str, str]],
        state: _RunState,
    ) -> list[RelationWrite]:
        out: dict[str, RelationWrite] = {}
        for d in drafts:
            src = resolved.get(d.source) or resolved.get(
                NameNormalizer.normalize(d.source)
            )
            tgt = resolved.get(d.target) or resolved.get(
                NameNormalizer.normalize(d.target)
            )
            if not src or not tgt or src[0] == tgt[0]:
                continue
            if not EvidencePolicy.is_grounded(d.evidence, unit.content):
                continue
            type_ = d.type if d.type in state.settings.relation_types else OTHER_TYPE
            rid = relation_id_for(unit.chunk_id, src[0], f"{d.kind}:{type_}", tgt[0])
            out[rid] = RelationWrite(
                id=rid,
                kind=d.kind,
                source_entity_id=src[0],
                target_entity_id=tgt[0],
                type=type_,
                evidence_text=d.evidence.strip(),
                source_decision_id=src[1],
                target_decision_id=tgt[1],
            )
        return list(out.values())
