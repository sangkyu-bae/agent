"""ExtractGraphUseCase — 추출 잡 실행 (Design §2.2 적재, Plan FR-04~07·FR-18).

module-3 판정은 임시(정규화 이름·타입 정확 일치면 연결, 아니면 새 엔티티).
"""
from __future__ import annotations

import dataclasses
from unittest.mock import MagicMock

import pytest
from src.application.graph_rag.extraction.use_case import ExtractGraphUseCase
from src.domain.graph_rag.extraction import (
    EXTRACTOR_VERSION,
    REL_REFERS_TO,
    ChunkUnit,
    ExtractionJob,
    ExtractionResult,
    JobMode,
    JobStatus,
    Mention,
    RelationDraft,
    TriggerSource,
)
from src.domain.graph_rag.interfaces import (
    ChunkSourcePort,
    ExtractionJobStorePort,
    GraphExtractorPort,
)
from src.domain.graph_rag.value_objects import GraphRagSettings, RolloutStage

from tests.application.graph_rag.fakes import FakeReader, FakeStore


class _Jobs(ExtractionJobStorePort):
    def __init__(self, job):
        self.job = job
        self.progress = []
        self.finished = None

    async def create(self, job, request_id):
        self.job = job
        return job

    async def get(self, job_id, request_id):
        return self.job

    async def find_active(self, document_id, request_id):
        return None

    async def latest_by_documents(self, document_ids, request_id):
        return {}

    async def mark_processing(self, job_id, total_chunks, request_id):
        self.job.status = JobStatus.PROCESSING
        self.job.total_chunks = total_chunks

    async def save_progress(self, job_id, counters, request_id):
        self.progress.append(dataclasses.replace(counters))

    async def finish(self, job_id, status, counters, error, request_id):
        self.finished = (status, dataclasses.replace(counters), error)

    async def fail_interrupted(self, request_id):
        return 0


class _Chunks(ChunkSourcePort):
    def __init__(self, units):
        self.units = units

    async def list_units(self, document_id, request_id):
        return self.units


class _Extractor(GraphExtractorPort):
    def __init__(self, by_chunk=None, *, fail_on=(), llm_calls=1):
        self.by_chunk = by_chunk or {}
        self.fail_on = set(fail_on)
        self.calls = []
        self._llm_calls = llm_calls

    async def extract(self, unit, context):
        self.calls.append(unit.chunk_id)
        if unit.chunk_id in self.fail_on:
            raise RuntimeError("llm error")
        mentions, relations = self.by_chunk.get(unit.chunk_id, ((), ()))
        return ExtractionResult(
            mentions=tuple(mentions), relations=tuple(relations),
            llm_calls=self._llm_calls,
        )


class _NoRules(GraphExtractorPort):
    async def extract(self, unit, context):
        return ExtractionResult()


def _unit(cid, idx=0, content="A상품은 개인사업자를 대상으로 한다."):
    return ChunkUnit(chunk_id=cid, document_id="doc-1", kb_id="kb-1",
                     collection_name="col", content=content, chunk_index=idx)


def _job(mode=JobMode.RESUME):
    return ExtractionJob(
        id="j1", document_id="doc-1", kb_id="kb-1", collection_name="col",
        status=JobStatus.PENDING, mode=mode, trigger_source=TriggerSource.ADMIN,
    )


def _settings(**over):
    base = dataclasses.replace(
        GraphRagSettings.defaults(), rollout_stage=RolloutStage.ADMIN_ONLY,
        extraction_enabled=True, extraction_llm_model_id="m-1",
        entity_types=("상품·서비스", "대상", "조문", "기타"),
        relation_types=("적용대상", "참조", "기타"),
    )
    return dataclasses.replace(base, **over)


def _m(name, type_="상품·서비스", cid="p1"):
    return Mention(name=name, type=type_, description="", chunk_id=cid)


def _uc(units, extractor, *, store=None, settings=None, mode=JobMode.RESUME,
        rules=None):
    jobs = _Jobs(_job(mode))
    store = store or FakeStore()
    uc = ExtractGraphUseCase(
        jobs=jobs, chunks=_Chunks(units), rule_extractor=rules or _NoRules(),
        llm_extractor=extractor, store=store,
        reader=FakeReader(settings or _settings()), logger=MagicMock(),
    )
    return uc, jobs, store


@pytest.mark.asyncio
async def test_happy_path_writes_entities_mentions_relations():
    ex = _Extractor({"p1": (
        [_m("A상품"), _m("개인사업자", "대상")],
        [RelationDraft("A상품", "개인사업자", "적용대상",
                       "A상품은 개인사업자를 대상으로", "p1")],
    )})
    uc, jobs, store = _uc([_unit("p1")], ex)
    await uc.run("j1", "r")
    status, counters, error = jobs.finished
    assert status is JobStatus.COMPLETED and error is None
    assert (counters.processed_chunks, counters.entities_created,
            counters.relations_created, counters.llm_calls) == (1, 2, 1, 1)
    assert len(store.entities) == 2 and len(store.relations) == 1
    assert store.chunks["p1"] == ("doc-1", EXTRACTOR_VERSION)
    assert jobs.job.total_chunks == 1


@pytest.mark.asyncio
async def test_ungrounded_relation_is_dropped():
    ex = _Extractor({"p1": (
        [_m("A상품"), _m("개인사업자", "대상")],
        [RelationDraft("A상품", "개인사업자", "적용대상", "원문에 없는 문장입니다", "p1")],
    )})
    uc, jobs, store = _uc([_unit("p1")], ex)
    await uc.run("j1", "r")
    assert store.relations == {}
    assert jobs.finished[1].relations_created == 0


@pytest.mark.asyncio
async def test_same_name_across_chunks_links_existing_entity():
    ex = _Extractor({
        "p1": ([_m("A상품", cid="p1")], []),
        "p2": ([_m(" A상품 ", cid="p2")], []),       # 정규화 후 같은 이름
        "p3": ([_m("A상품", "대상", cid="p3")], []),  # 타입이 다르면 다른 엔티티
    })
    uc, jobs, store = _uc([_unit("p1", 0), _unit("p2", 1), _unit("p3", 2)], ex)
    await uc.run("j1", "r")
    c = jobs.finished[1]
    assert c.entities_created == 2 and c.entities_linked == 1
    assert len(store.entities) == 2 and len(store.mentions) == 3


@pytest.mark.asyncio
async def test_rule_relations_use_refers_to_and_merge_with_llm():
    class _Rules(GraphExtractorPort):
        async def extract(self, unit, context):
            return ExtractionResult(
                mentions=(
                    Mention("제5조", "조문", "", unit.chunk_id, key="doc-1::제5조"),
                    Mention("제3조", "조문", "", unit.chunk_id, key="doc-1::제3조"),
                ),
                relations=(RelationDraft(
                    "doc-1::제5조", "doc-1::제3조", "참조", "제5조 제3조에 따른",
                    unit.chunk_id, kind=REL_REFERS_TO,
                ),),
            )

    unit = _unit("p1", content="제5조 제3조에 따른 대상자")
    uc, jobs, store = _uc([unit], _Extractor({"p1": ([_m("대상자", "대상")], [])}),
                          rules=_Rules())
    await uc.run("j1", "r")
    kinds = [r.kind for r, _ in store.relations.values()]
    assert kinds == [REL_REFERS_TO]
    assert len(store.entities) == 3


@pytest.mark.asyncio
async def test_unknown_types_become_other():
    ex = _Extractor({"p1": ([_m("A상품", "목록밖타입")], [])})
    uc, _, store = _uc([_unit("p1")], ex)
    await uc.run("j1", "r")
    assert [e.type for e in store.entities.values()] == ["기타"]


@pytest.mark.asyncio
async def test_resume_skips_already_extracted_chunks():
    store = FakeStore()
    store._graph().chunks["p1"] = ("doc-1", EXTRACTOR_VERSION)
    ex = _Extractor({"p2": ([_m("B상품")], [])})
    uc, jobs, _ = _uc([_unit("p1", 0), _unit("p2", 1)], ex, store=store)
    await uc.run("j1", "r")
    assert ex.calls == ["p2"]
    assert jobs.finished[1].processed_chunks == 2  # 건너뛴 청크도 완료로 센다


@pytest.mark.asyncio
async def test_rebuild_deletes_document_graph_first():
    store = FakeStore()
    g = store._graph()
    g.chunks["p1"] = ("doc-1", EXTRACTOR_VERSION)
    ex = _Extractor({"p1": ([_m("A상품")], [])})
    uc, _, _ = _uc([_unit("p1")], ex, store=store, mode=JobMode.REBUILD)
    await uc.run("j1", "r")
    assert ex.calls == ["p1"]  # rebuild 는 건너뛰지 않는다


@pytest.mark.asyncio
async def test_chunk_failures_make_partial_and_all_failed_makes_failed():
    ex = _Extractor({"p1": ([_m("A상품")], [])}, fail_on={"p2"})
    uc, jobs, _ = _uc([_unit("p1", 0), _unit("p2", 1)], ex)
    await uc.run("j1", "r")
    assert jobs.finished[0] is JobStatus.PARTIAL
    assert jobs.finished[1].failed_chunks == 1

    ex2 = _Extractor(fail_on={"p1"})
    uc2, jobs2, _ = _uc([_unit("p1")], ex2)
    await uc2.run("j1", "r")
    assert jobs2.finished[0] is JobStatus.FAILED


@pytest.mark.asyncio
async def test_llm_budget_stops_and_marks_partial():
    units = [_unit(f"p{i}", i) for i in range(5)]
    ex = _Extractor({u.chunk_id: ([_m(f"상품{u.chunk_id}")], []) for u in units})
    uc, jobs, _ = _uc(units, ex, settings=_settings(max_llm_calls_per_doc=2,
                                                    concurrency=1))
    await uc.run("j1", "r")
    status, counters, error = jobs.finished
    assert status is JobStatus.PARTIAL and "budget" in error
    assert counters.llm_calls == 2 and len(ex.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("over, reason", [
    ({"rollout_stage": RolloutStage.OFF}, "stage_off"),
    ({"extraction_llm_model_id": None}, "model"),
])
async def test_preconditions_fail_job(over, reason):
    uc, jobs, _ = _uc([_unit("p1")], _Extractor(), settings=_settings(**over))
    await uc.run("j1", "r")
    assert jobs.finished[0] is JobStatus.FAILED and reason in jobs.finished[2]


@pytest.mark.asyncio
async def test_store_unavailable_fails_job():
    uc, jobs, _ = _uc([_unit("p1")], _Extractor({"p1": ([_m("A")], [])}),
                      store=FakeStore(down=True))
    await uc.run("j1", "r")
    assert jobs.finished[0] is JobStatus.FAILED


@pytest.mark.asyncio
async def test_no_units_completes_with_zero():
    uc, jobs, _ = _uc([], _Extractor())
    await uc.run("j1", "r")
    assert jobs.finished[0] is JobStatus.COMPLETED
    assert jobs.job.total_chunks == 0
