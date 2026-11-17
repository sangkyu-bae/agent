"""ExtractGraphUseCase — 문서 1건의 그래프 추출 잡 실행.

Design Ref: graph-rag-foundation §2.2(적재)·§3.4·§6.2, Plan FR-04~07·FR-18.
- LLM 추출은 동시 실행(설정 concurrency), 판정·쓰기는 잠금으로 직렬화한다
  (같은 새 엔티티를 두 청크가 동시에 만드는 경합 방지).
- 청크 실패는 세고 계속 진행한다. 호출 상한에 닿으면 남은 청크는 건너뛰고 partial.
- module-3 판정은 임시: (scope, 정규화 키, 타입) 정확 일치면 연결, 아니면 새 엔티티.
  module-4 에서 후보 검색 + Jev/LLM 판정으로 바뀐다.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field

from src.domain.graph_rag.exceptions import GraphBackendUnavailableError
from src.domain.graph_rag.extraction import (
    EXTRACTOR_VERSION,
    GLOBAL_SCOPE,
    ChunkGraphWrite,
    ChunkUnit,
    EntityWrite,
    EvidencePolicy,
    ExtractionContext,
    ExtractionJob,
    ExtractionResult,
    JobCounters,
    JobMode,
    JobStatus,
    LiteralValuePolicy,
    Mention,
    MentionWrite,
    NameNormalizer,
    RelationDraft,
    RelationWrite,
    decision_id_for,
    relation_id_for,
)
from src.domain.graph_rag.interfaces import (
    ChunkSourcePort,
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
    known: dict[tuple[str, str], str] = field(default_factory=dict)  # (key,type)->id
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
        logger: LoggerInterface,
    ) -> None:
        self._jobs = jobs
        self._chunks = chunks
        self._rules = rule_extractor
        self._llm = llm_extractor
        self._store = store
        self._reader = reader
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
                await self._write(unit, result, state)
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
        self, unit: ChunkUnit, result: ExtractionResult, state: _RunState
    ) -> None:
        resolved, new_entities = await self._resolve_all(result.mentions, state)
        relations = self._relations(unit, result.relations, resolved, state)
        await self._store.write_chunk_graph(
            ChunkGraphWrite(  # type: ignore[union-attr]
                unit=unit,
                extractor_version=EXTRACTOR_VERSION,
                new_entities=tuple(new_entities),
                mentions=tuple(
                    MentionWrite(eid, did) for eid, did in resolved.values()
                ),
                relations=tuple(relations),
            )
        )
        state.counters.entities_created += len(new_entities)
        state.counters.entities_linked += len(resolved) - len(new_entities)
        state.counters.relations_created += len(relations)
        for e in new_entities:
            state.known[(e.normalized_name, e.type)] = e.id

    def _type(self, mention: Mention, state: _RunState) -> str:
        t = (mention.type or "").strip()
        return t if t in state.settings.entity_types else OTHER_TYPE

    async def _resolve_all(
        self, mentions: tuple[Mention, ...], state: _RunState
    ) -> tuple[dict[str, tuple[str, str]], list[EntityWrite]]:
        """정규화 키 → (entity_id, decision_id). 같은 청크 안 중복 언급은 하나로.

        값 이름(LiteralValuePolicy)은 저장 키를 청크 단위로 바꿔 청크 밖과 연결하지
        않는다(2026-11-17 개선). 관계 끝점 조회용 키는 그대로 둔다.
        """
        resolved: dict[str, tuple[str, str]] = {}
        new_entities: list[EntityWrite] = []
        for m in mentions:
            key, type_ = m.lookup_key, self._type(m, state)
            if not key or key in resolved:
                continue
            if m.key is None and LiteralValuePolicy.is_literal(m.name):
                key_in_store = f"{m.chunk_id}::{key}"
            else:
                key_in_store = key
            entity_id = state.known.get(
                (key_in_store, type_)
            ) or await self._store.find_entity_id(  # type: ignore[union-attr]
                GLOBAL_SCOPE, key_in_store, type_
            )
            if entity_id is None:
                entity_id = str(uuid.uuid4())
                new_entities.append(
                    EntityWrite(
                        id=entity_id,
                        scope_key=GLOBAL_SCOPE,
                        name=m.name,
                        normalized_name=key_in_store,
                        type=type_,
                        description=m.description,
                    )
                )
            resolved[key] = (entity_id, decision_id_for(m.chunk_id, key, type_))
        return resolved, new_entities

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
