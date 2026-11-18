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

from src.application.graph_rag.resolution.resolver import EntityResolver
from src.domain.graph_rag.interfaces import EntityChooserPort, EntityEmbedderPort
from src.domain.graph_rag.resolution import NEW_LABEL, ChooserVerdict, LlmConfidence

from tests.application.graph_rag.fakes import FakeDecisions, FakeReader, FakeStore


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


class _Embedder(EntityEmbedderPort):
    """이름마다 다른 단위 벡터 — 같은 이름만 유사도 1, 다른 이름은 0."""

    async def embed(self, texts):
        import hashlib

        def one_hot(t):
            i = int(hashlib.md5(t.encode()).hexdigest(), 16) % 256
            return [1.0 if j == i else 0.0 for j in range(256)]

        return [one_hot(t) for t in texts]


class _NewChooser(EntityChooserPort):
    async def choose(self, mention, context, candidates, request_id):
        return ChooserVerdict(NEW_LABEL, confidence=LlmConfidence.HIGH)


def _uc(units, extractor, *, store=None, settings=None, mode=JobMode.RESUME,
        rules=None):
    jobs = _Jobs(_job(mode))
    store = store or FakeStore()
    resolver = EntityResolver(store=store, embedder=_Embedder(),
                              llm_chooser=_NewChooser(), jev_chooser=None,
                              logger=MagicMock())
    uc = ExtractGraphUseCase(
        jobs=jobs, chunks=_Chunks(units), rule_extractor=rules or _NoRules(),
        llm_extractor=extractor, store=store,
        reader=FakeReader(settings or _settings()), resolver=resolver,
        decisions=FakeDecisions(), logger=MagicMock(),
    )
    uc.decisions = uc._decisions
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
    # 판정 기록(V089)이 언급마다 남고, 그래프 언급 엣지의 decision_id 와 같다
    decision_ids = set(uc.decisions.rows)
    assert len(decision_ids) == 2
    assert {m[2] for m in store.mentions} == decision_ids


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
async def test_literal_values_are_not_linked_across_chunks():
    # 2026-11-17 개선: "연 4.2%" 같은 값은 청크 밖과 연결하지 않는다
    ex = _Extractor({
        "p1": ([_m("연 4.2%", "대상", cid="p1"), _m("A상품", cid="p1")], []),
        "p2": ([_m("연 4.2%", "대상", cid="p2"), _m("A상품", cid="p2")], []),
    })
    uc, jobs, store = _uc([_unit("p1", 0), _unit("p2", 1)], ex)
    await uc.run("j1", "r")
    values = [e for e in store.entities.values() if e.name == "연 4.2%"]
    products = [e for e in store.entities.values() if e.name == "A상품"]
    assert len(values) == 2 and len(products) == 1
    assert jobs.finished[1].entities_linked == 1  # A상품만 연결


@pytest.mark.asyncio
async def test_llm_type_wins_for_rule_title_and_title_relation_resolves():
    class _Rules(GraphExtractorPort):
        async def extract(self, unit, context):
            return ExtractionResult(
                mentions=(
                    Mention("제12조", "조문", "", unit.chunk_id, key="doc-1::제12조"),
                    Mention("운전자금대출 한도", "용어", "", unit.chunk_id),
                ),
                relations=(RelationDraft(
                    "doc-1::제12조", "운전자금대출 한도", "기타",
                    "제12조(운전자금대출 한도)", unit.chunk_id,
                ),),
            )

    unit = _unit("p1", content="제12조(운전자금대출 한도) 한도는 30% 이내로 한다.")
    ex = _Extractor({"p1": ([_m("운전자금대출 한도", "대상")], [])})
    uc, _, store = _uc([unit], ex, rules=_Rules())
    await uc.run("j1", "r")
    titles = [e for e in store.entities.values() if e.name == "운전자금대출 한도"]
    assert len(titles) == 1 and titles[0].type == "대상"  # LLM 타입 우선
    (rel, _), = store.relations.values()
    assert rel.target_entity_id == titles[0].id


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


# ── module-4b: 주제 분류 연결 ───────────────────────────────────────────────

class _Topics:
    """DocumentTopicClassifier 대역 — classify·current 호출만 기록."""

    def __init__(self, ids=("t-loan",), current=(), exc=None, llm_calls=1):
        self.ids, self._current, self.exc, self.llm_calls = list(ids), list(current), exc, llm_calls
        self.classified = []

    async def current(self, document_id, request_id):
        return list(self._current)

    async def classify(self, *, job_id, document_id, units, settings, state, request_id):
        from src.application.graph_rag.topic.classifier import TopicRunResult

        self.classified.append(document_id)
        if self.exc:
            raise self.exc
        return TopicRunResult(topic_ids=list(self.ids), llm_calls=self.llm_calls,
                              judge_calls=1)


def _uc_topics(topics, mode=JobMode.RESUME):
    uc, jobs, store = _uc([_unit("p1")], _Extractor({"p1": ([_m("A상품")], [])}),
                          mode=mode)
    uc._topics = topics
    return uc, jobs, store


@pytest.mark.asyncio
async def test_rebuild_classifies_topics_and_copies_ids_to_chunks():
    topics = _Topics(current=("t-old",))
    uc, jobs, store = _uc_topics(topics, mode=JobMode.REBUILD)
    await uc.run("j1", "r")
    status, counters, _ = jobs.finished
    assert status is JobStatus.COMPLETED
    assert topics.classified == ["doc-1"]
    assert store.doc_topics["doc-1"] == ["t-loan"]
    assert (counters.llm_calls, counters.judge_calls) == (2, 1)  # 청크 1 + 주제 1


@pytest.mark.asyncio
async def test_resume_with_existing_topics_skips_classification():
    topics = _Topics(current=("t-old",))
    uc, _, store = _uc_topics(topics)
    await uc.run("j1", "r")
    assert topics.classified == []
    assert store.doc_topics["doc-1"] == ["t-old"]


@pytest.mark.asyncio
async def test_resume_without_topics_classifies():
    topics = _Topics()
    uc, _, store = _uc_topics(topics)
    await uc.run("j1", "r")
    assert topics.classified == ["doc-1"] and store.doc_topics["doc-1"] == ["t-loan"]


@pytest.mark.asyncio
async def test_topic_failure_does_not_fail_job():
    topics = _Topics(exc=RuntimeError("llm down"))
    uc, jobs, store = _uc_topics(topics, mode=JobMode.REBUILD)
    await uc.run("j1", "r")
    status, counters, _ = jobs.finished
    assert status is JobStatus.COMPLETED and counters.processed_chunks == 1
    assert store.doc_topics["doc-1"] == []


@pytest.mark.asyncio
async def test_without_topic_classifier_nothing_changes():
    uc, jobs, store = _uc([_unit("p1")], _Extractor({"p1": ([_m("A상품")], [])}))
    await uc.run("j1", "r")
    assert jobs.finished[0] is JobStatus.COMPLETED
    assert not hasattr(store, "doc_topics")
