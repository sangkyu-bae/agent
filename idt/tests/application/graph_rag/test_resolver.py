"""EntityResolver — 후보 검색 + Jev 세 구간 + LLM 재판정·대체 (Design §2.2 판정, FR-08~10)."""
from __future__ import annotations

import dataclasses
from unittest.mock import MagicMock

import pytest
from src.application.graph_rag.resolution.resolver import EntityResolver, ResolveRunState
from src.domain.graph_rag.extraction import ChunkUnit, EntityWrite, Mention
from src.domain.graph_rag.interfaces import EntityChooserPort, EntityEmbedderPort
from src.domain.graph_rag.resolution import (
    NEW_LABEL,
    ChooserVerdict,
    DecidedBy,
    LlmConfidence,
    ResolutionBand,
    ReviewStatus,
)
from src.domain.graph_rag.value_objects import GraphRagSettings
from src.domain.judgment.exceptions import JudgmentUnavailableError
from src.domain.judgment.value_objects import JudgmentBackendKind

from tests.application.graph_rag.fakes import FakeStore

_UNIT = ChunkUnit(chunk_id="p9", document_id="doc-2", kb_id="kb", collection_name="c",
                  content="A 상품은 개인사업자를 대상으로 한다.", chunk_index=0)


class _Embedder(EntityEmbedderPort):
    def __init__(self, vectors=None, fail=False):
        self.vectors = vectors or {}
        self.fail = fail
        self.calls = []

    async def embed(self, texts):
        self.calls.append(list(texts))
        if self.fail:
            raise RuntimeError("embedding down")
        return [list(self.vectors.get(t, (0.0, 1.0))) for t in texts]


class _Chooser(EntityChooserPort):
    def __init__(self, verdict=None, exc=None):
        self.verdict = verdict
        self.exc = exc
        self.calls = []

    async def choose(self, mention, context, candidates, request_id):
        self.calls.append((mention.name, dict(candidates)))
        if self.exc:
            raise self.exc
        return self.verdict


def _settings(**over):
    base = dataclasses.replace(
        GraphRagSettings.defaults(), jev_enabled=True,
        entity_types=("상품", "대상", "기타"),
    )
    return dataclasses.replace(base, **over)


def _store_with(name="A상품", type_="상품", vec=(1.0, 0.0)):
    store = FakeStore()
    store._ensure4()
    store.entities["e1"] = EntityWrite("e1", "global", name, name.lower(), type_, "",
                                       name_embedding=vec)
    return store


def _m(name, type_="상품"):
    return Mention(name=name, type=type_, description="", chunk_id="p9")


async def _resolve(store, mentions, *, jev=None, llm=None, embedder=None, settings=None,
                   state=None):
    resolver = EntityResolver(
        store=store, embedder=embedder or _Embedder({"A 상품": (0.99, 0.14)}),
        llm_chooser=llm or _Chooser(ChooserVerdict(NEW_LABEL, confidence=LlmConfidence.HIGH)),
        jev_chooser=jev, logger=MagicMock(),
    )
    return await resolver.resolve_chunk(
        mentions, _UNIT, job_id="j1", settings=settings or _settings(),
        state=state or ResolveRunState(), request_id="r",
    )


@pytest.mark.asyncio
async def test_no_candidates_creates_new_with_embedding():
    out = await _resolve(FakeStore(), [_m("새상품")])
    (o,) = out
    assert o.new_entity is not None and o.new_entity.name_embedding is not None
    assert o.decision.decided_by is DecidedBy.RULE
    assert o.decision.band is ResolutionBand.AUTO_NEW and o.decision.created_new


@pytest.mark.asyncio
async def test_exact_match_links_without_judge():
    jev = _Chooser()
    (o,) = await _resolve(_store_with(), [_m("A상품")], jev=jev)
    assert o.entity_id == "e1" and o.new_entity is None and o.alias is None
    assert o.decision.decided_by is DecidedBy.RULE and jev.calls == []


@pytest.mark.asyncio
async def test_jev_high_probability_links_and_adds_alias():
    jev = _Chooser(ChooserVerdict("C1", probabilities={"C1": 0.9, NEW_LABEL: 0.1}))
    (o,) = await _resolve(_store_with(), [_m("A 상품")], jev=jev)
    assert o.entity_id == "e1" and o.judge_calls == 1
    assert o.decision.decided_by is DecidedBy.JEV
    assert o.decision.band is ResolutionBand.AUTO_LINK
    assert o.decision.review_status is ReviewStatus.NONE
    assert o.alias is not None and o.alias.surface == "A 상품"


@pytest.mark.asyncio
async def test_jev_low_probability_creates_new():
    jev = _Chooser(ChooserVerdict(NEW_LABEL, probabilities={"C1": 0.2, NEW_LABEL: 0.8}))
    (o,) = await _resolve(_store_with(), [_m("A 상품")], jev=jev)
    assert o.new_entity is not None
    assert o.decision.band is ResolutionBand.AUTO_NEW and o.decision.probability == 0.2


@pytest.mark.asyncio
async def test_jev_middle_band_rejudged_by_llm_and_pending():
    jev = _Chooser(ChooserVerdict("C1", probabilities={"C1": 0.6, NEW_LABEL: 0.4}))
    llm = _Chooser(ChooserVerdict("C1", confidence=LlmConfidence.MEDIUM, reason="같은 상품"))
    (o,) = await _resolve(_store_with(), [_m("A 상품")], jev=jev, llm=llm)
    assert o.entity_id == "e1" and o.llm_calls == 1
    assert o.decision.decided_by is DecidedBy.LLM_REJUDGE
    assert o.decision.band is ResolutionBand.REJUDGE
    assert o.decision.review_status is ReviewStatus.PENDING
    assert o.decision.llm_reason == "같은 상품"


@pytest.mark.asyncio
@pytest.mark.parametrize("jev_enabled, jev, decided", [
    (False, _Chooser(), DecidedBy.LLM_FALLBACK),     # 관리자 설정에서 Jev off
    (True, None, DecidedBy.LLM_FALLBACK),            # 백엔드 미조립
    (True, _Chooser(exc=JudgmentUnavailableError(JudgmentBackendKind.JEV, "x")),
     DecidedBy.LLM_FALLBACK),                        # 호출 실패
])
async def test_llm_fallback_when_jev_unavailable(jev_enabled, jev, decided):
    llm = _Chooser(ChooserVerdict("C1", confidence=LlmConfidence.HIGH))
    (o,) = await _resolve(_store_with(), [_m("A 상품")], jev=jev, llm=llm,
                          settings=_settings(jev_enabled=jev_enabled))
    assert o.decision.decided_by is decided
    assert o.decision.band is ResolutionBand.FALLBACK
    assert o.decision.review_status is ReviewStatus.NONE  # high 확신은 검토 없음
    assert o.entity_id == "e1"


@pytest.mark.asyncio
async def test_fallback_low_confidence_goes_to_review():
    llm = _Chooser(ChooserVerdict("C1", confidence=LlmConfidence.LOW))
    (o,) = await _resolve(_store_with(), [_m("A 상품")], llm=llm,
                          settings=_settings(jev_enabled=False))
    assert o.decision.review_status is ReviewStatus.PENDING


@pytest.mark.asyncio
async def test_llm_failure_creates_new_and_pending():
    llm = _Chooser(exc=RuntimeError("llm down"))
    (o,) = await _resolve(_store_with(), [_m("A 상품")], llm=llm,
                          settings=_settings(jev_enabled=False))
    assert o.new_entity is not None
    assert o.decision.review_status is ReviewStatus.PENDING


@pytest.mark.asyncio
async def test_incompatible_type_candidates_are_excluded():
    jev = _Chooser()
    (o,) = await _resolve(_store_with(type_="대상"), [_m("A 상품", "상품")], jev=jev)
    assert jev.calls == [] and o.new_entity is not None


@pytest.mark.asyncio
async def test_literal_values_skip_search_and_judge():
    embedder, jev = _Embedder(), _Chooser()
    (o,) = await _resolve(FakeStore(), [_m("연 4.2%", "기타")], jev=jev, embedder=embedder)
    assert o.new_entity.normalized_name == "p9::연 4.2%"
    assert embedder.calls == [] and jev.calls == []


@pytest.mark.asyncio
async def test_jev_disabled_for_job_after_consecutive_failures():
    state = ResolveRunState()
    jev = _Chooser(exc=JudgmentUnavailableError(JudgmentBackendKind.JEV, "x"))
    llm = _Chooser(ChooserVerdict("C1", confidence=LlmConfidence.HIGH))
    for _ in range(6):
        await _resolve(_store_with(), [_m("A 상품")], jev=jev, llm=llm, state=state)
    assert len(jev.calls) == 5  # 5회 연속 실패 후 이 잡에서는 Jev 생략


@pytest.mark.asyncio
async def test_embedding_failure_falls_back_to_exact_only():
    (o,) = await _resolve(_store_with(), [_m("A상품")], embedder=_Embedder(fail=True))
    assert o.entity_id == "e1"


@pytest.mark.asyncio
async def test_duplicate_mentions_in_chunk_resolved_once():
    out = await _resolve(FakeStore(), [_m("새상품"), _m(" 새상품 ")])
    assert len(out) == 1
