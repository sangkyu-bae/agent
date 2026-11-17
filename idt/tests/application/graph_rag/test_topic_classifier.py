"""DocumentTopicClassifier — 문서 주제 자동 분류 (Design §11.9, FR-25~28)."""
from __future__ import annotations

import dataclasses
from unittest.mock import MagicMock

import pytest

from src.application.graph_rag.resolution.resolver import ResolveRunState
from src.application.graph_rag.topic.classifier import DocumentTopicClassifier
from src.domain.graph_rag.extraction import ChunkUnit
from src.domain.graph_rag.interfaces import EntityChooserPort, TopicProposerPort
from src.domain.graph_rag.resolution import (
    ChooserVerdict,
    DecidedBy,
    LlmConfidence,
    ResolutionBand,
    ReviewStatus,
)
from src.domain.graph_rag.topic import (
    DOCUMENT_CHUNK_ID,
    Topic,
    TopicLevel,
    TopicOrigin,
    TopicProposal,
    TopicStatus,
    TopicSuggestion,
    topic_decision_id,
)
from src.domain.graph_rag.value_objects import GraphRagSettings

from tests.application.graph_rag.fakes import (
    FakeDecisions,
    FakeDocumentTopics,
    FakeTopics,
)

_UNITS = [ChunkUnit("c0", "doc-1", "kb", "col", "여신 취급 규정 제1조(목적)", 0)]


def _topic(id_, name, level=TopicLevel.MAJOR, parent=None,
           status=TopicStatus.ACTIVE, origin=TopicOrigin.ADMIN):
    return Topic(id_, name, name.casefold(), level, parent, f"{name} 관련",
                 status, origin)


class _Proposer(TopicProposerPort):
    def __init__(self, proposal=None, exc=None):
        self.proposal = proposal
        self.exc = exc
        self.excerpts = []

    async def propose(self, excerpt, request_id):
        self.excerpts.append(excerpt)
        if self.exc:
            raise self.exc
        return self.proposal


class _Chooser(EntityChooserPort):
    def __init__(self, verdicts=None, exc=None):
        self.verdicts = list(verdicts or [])
        self.exc = exc
        self.calls = []

    async def choose(self, mention, context, candidates, request_id):
        self.calls.append((mention, dict(candidates)))
        if self.exc:
            raise self.exc
        return self.verdicts.pop(0)


def _proposal(major="여신", minor="기업여신", secondary=()):
    return TopicProposal(
        major=TopicSuggestion(major, f"{major} 업무"),
        minor=TopicSuggestion(minor, f"{minor} 업무") if minor else None,
        secondary=tuple(secondary),
    )


def _settings(**over):
    base = dataclasses.replace(GraphRagSettings.defaults(), jev_enabled=True)
    return dataclasses.replace(base, **over)


def _make(topics=(), proposal=None, jev=None, llm=None, proposer=None):
    repo, links, decisions = FakeTopics(topics), FakeDocumentTopics(), FakeDecisions()
    clf = DocumentTopicClassifier(
        topics=repo,
        document_topics=links,
        decisions=decisions,
        proposer=proposer or _Proposer(proposal or _proposal()),
        llm_chooser=llm or _Chooser(),
        jev_chooser=jev,
        logger=MagicMock(),
    )
    return clf, repo, links, decisions


async def _run(clf, settings=None, state=None):
    return await clf.classify(
        job_id="job-1", document_id="doc-1", units=_UNITS,
        settings=settings or _settings(), state=state or ResolveRunState(),
        request_id="r",
    )


@pytest.mark.asyncio
async def test_empty_list_creates_pending_auto_topics_and_links_primary():
    clf, repo, links, decisions = _make()
    result = await _run(clf)

    major = next(t for t in repo.rows.values() if t.level is TopicLevel.MAJOR)
    minor = next(t for t in repo.rows.values() if t.level is TopicLevel.MINOR)
    assert (major.name, major.status, major.origin) == (
        "여신", TopicStatus.PENDING, TopicOrigin.AUTO)
    assert minor.parent_id == major.id
    assert result.topic_ids == [major.id, minor.id]
    assert [(lk.topic_id, lk.is_primary) for lk in links.links["doc-1"]] == [
        (major.id, True), (minor.id, True)]
    d = decisions.rows[topic_decision_id("doc-1", "major")]
    assert (d.decided_by, d.band, d.created_new, d.review_status) == (
        DecidedBy.RULE, ResolutionBand.AUTO_NEW, True, ReviewStatus.PENDING)
    assert (d.chunk_id, d.mention_type, d.entity_id) == (
        DOCUMENT_CHUNK_ID, "주제:대분류", major.id)


@pytest.mark.asyncio
async def test_exact_name_links_existing_without_judge():
    jev, llm = _Chooser(), _Chooser()
    clf, repo, links, decisions = _make(
        topics=[_topic("t-loan", "여신"), _topic("t-corp", "기업여신",
                                                 TopicLevel.MINOR, "t-loan")],
        jev=jev, llm=llm,
    )
    result = await _run(clf)
    assert result.topic_ids == ["t-loan", "t-corp"]
    assert jev.calls == [] and llm.calls == []
    d = decisions.rows[topic_decision_id("doc-1", "major")]
    assert (d.decided_by, d.band, d.review_status) == (
        DecidedBy.RULE, ResolutionBand.AUTO_LINK, ReviewStatus.NONE)


@pytest.mark.asyncio
async def test_jev_high_probability_links_existing_major():
    jev = _Chooser([
        ChooserVerdict("C1", probabilities={"C1": 0.93, "C2": 0.02, "NEW": 0.05}),
    ])
    clf, repo, links, decisions = _make(
        topics=[_topic("t-loan", "대출"), _topic("t-dep", "수신")],
        proposal=_proposal(major="여신", minor=None), jev=jev,
    )
    result = await _run(clf)
    assert result.topic_ids == ["t-loan"]
    assert result.judge_calls == 1
    mention, candidates = jev.calls[0]
    assert mention.name == "여신" and set(candidates) == {"C1", "C2"}
    d = decisions.rows[topic_decision_id("doc-1", "major")]
    assert (d.decided_by, d.band, d.chosen_label) == (
        DecidedBy.JEV, ResolutionBand.AUTO_LINK, "C1")
    assert links.links["doc-1"][0].probability == pytest.approx(0.93)


@pytest.mark.asyncio
async def test_jev_low_probability_creates_new_topic_for_review():
    jev = _Chooser([ChooserVerdict("NEW", probabilities={"C1": 0.1, "NEW": 0.9})])
    clf, repo, _, decisions = _make(
        topics=[_topic("t-hr", "인사")], proposal=_proposal(minor=None), jev=jev,
    )
    result = await _run(clf)
    new = repo.rows[result.topic_ids[0]]
    assert (new.name, new.status) == ("여신", TopicStatus.PENDING)
    d = decisions.rows[topic_decision_id("doc-1", "major")]
    assert (d.decided_by, d.band, d.review_status) == (
        DecidedBy.JEV, ResolutionBand.AUTO_NEW, ReviewStatus.PENDING)


@pytest.mark.asyncio
async def test_jev_middle_band_rejudged_by_llm_and_pending():
    jev = _Chooser([ChooserVerdict("C1", probabilities={"C1": 0.6, "NEW": 0.4})])
    llm = _Chooser([ChooserVerdict("C1", confidence=LlmConfidence.HIGH, reason="같음")])
    clf, _, _, decisions = _make(
        topics=[_topic("t-loan", "대출")], proposal=_proposal(minor=None),
        jev=jev, llm=llm,
    )
    result = await _run(clf)
    assert result.topic_ids == ["t-loan"]
    d = decisions.rows[topic_decision_id("doc-1", "major")]
    assert (d.decided_by, d.band, d.review_status) == (
        DecidedBy.LLM_REJUDGE, ResolutionBand.REJUDGE, ReviewStatus.PENDING)
    assert result.llm_calls == 2  # 제안 1 + 재판정 1


@pytest.mark.asyncio
async def test_jev_off_uses_llm_fallback_high_confidence_no_review():
    jev = _Chooser()
    llm = _Chooser([ChooserVerdict("C1", confidence=LlmConfidence.HIGH)])
    clf, _, _, decisions = _make(
        topics=[_topic("t-loan", "대출")], proposal=_proposal(minor=None),
        jev=jev, llm=llm,
    )
    result = await _run(clf, settings=_settings(jev_enabled=False))
    assert jev.calls == [] and result.topic_ids == ["t-loan"]
    d = decisions.rows[topic_decision_id("doc-1", "major")]
    assert (d.decided_by, d.band, d.review_status) == (
        DecidedBy.LLM_FALLBACK, ResolutionBand.FALLBACK, ReviewStatus.NONE)


@pytest.mark.asyncio
async def test_jev_error_falls_back_to_llm_and_counts_failure():
    state = ResolveRunState()
    llm = _Chooser([ChooserVerdict("C1", confidence=LlmConfidence.MEDIUM)])
    clf, _, _, decisions = _make(
        topics=[_topic("t-loan", "대출")], proposal=_proposal(minor=None),
        jev=_Chooser(exc=TimeoutError()), llm=llm,
    )
    await _run(clf, state=state)
    assert state.jev_failures == 1
    d = decisions.rows[topic_decision_id("doc-1", "major")]
    assert (d.decided_by, d.review_status) == (
        DecidedBy.LLM_FALLBACK, ReviewStatus.PENDING)


@pytest.mark.asyncio
async def test_llm_error_creates_new_topic_pending():
    clf, repo, _, decisions = _make(
        topics=[_topic("t-loan", "대출")], proposal=_proposal(minor=None),
        llm=_Chooser(exc=RuntimeError("llm down")),
    )
    result = await _run(clf, settings=_settings(jev_enabled=False))
    assert repo.rows[result.topic_ids[0]].name == "여신"
    d = decisions.rows[topic_decision_id("doc-1", "major")]
    assert d.created_new and d.review_status is ReviewStatus.PENDING


@pytest.mark.asyncio
async def test_secondary_links_existing_only_max_two_and_skips_primary():
    llm = _Chooser()
    clf, repo, links, _ = _make(
        topics=[_topic("t-loan", "여신"), _topic("t-cust", "고객"),
                _topic("t-risk", "리스크"), _topic("t-hr", "인사")],
        proposal=_proposal(minor=None,
                           secondary=("여신", "고객", "외환", "리스크", "인사")),
        llm=llm,
    )
    result = await _run(clf)
    # 대표와 같은 이름은 빼고 앞 2개(고객·외환)만 본다. 없는 '외환'은 만들지 않는다.
    # 보조 주제에는 LLM 을 부르지 않는다(Jev 가 없으면 정확 일치만).
    assert result.topic_ids == ["t-loan", "t-cust"]
    assert llm.calls == []
    assert [(lk.topic_id, lk.is_primary) for lk in links.links["doc-1"]] == [
        ("t-loan", True), ("t-cust", False)]
    assert all(t.name != "외환" for t in repo.rows.values())


@pytest.mark.asyncio
async def test_retired_topics_are_not_candidates():
    clf, repo, _, decisions = _make(
        topics=[_topic("t-old", "여신", status=TopicStatus.RETIRED),
                _topic("t-other", "인사", status=TopicStatus.RETIRED)],
        proposal=_proposal(minor=None),
    )
    result = await _run(clf)
    # 후보가 없어 새로 만들려 했지만 같은 이름의 폐기 주제가 있어(유일 키) 되살린다
    assert result.topic_ids == ["t-old"]
    assert repo.rows["t-old"].status is TopicStatus.PENDING
    assert repo.rows["t-other"].status is TopicStatus.RETIRED
    d = decisions.rows[topic_decision_id("doc-1", "major")]
    assert d.created_new and d.decided_by is DecidedBy.RULE


@pytest.mark.asyncio
async def test_minor_is_judged_only_under_chosen_major():
    llm = _Chooser([ChooserVerdict("C1", confidence=LlmConfidence.HIGH)])
    clf, _, _, _ = _make(
        topics=[
            _topic("t-loan", "여신"),
            _topic("t-corp", "법인대출", TopicLevel.MINOR, "t-loan"),
            _topic("t-x", "예금상품", TopicLevel.MINOR, "t-dep"),
        ],
        llm=llm,
    )
    result = await _run(clf, settings=_settings(jev_enabled=False))
    _, candidates = llm.calls[0]
    assert [c.entity_id for c in candidates.values()] == ["t-corp"]
    assert result.topic_ids == ["t-loan", "t-corp"]


@pytest.mark.asyncio
async def test_empty_document_skips_classification():
    proposer = _Proposer(_proposal())
    clf, _, links, _ = _make(proposer=proposer)
    result = await clf.classify(
        job_id="j", document_id="doc-1",
        units=[ChunkUnit("c0", "doc-1", "kb", "col", "   ", 0)],
        settings=_settings(), state=ResolveRunState(), request_id="r",
    )
    assert result.topic_ids == [] and proposer.excerpts == [] and links.links == {}


@pytest.mark.asyncio
async def test_proposer_error_propagates():
    clf, _, _, _ = _make(proposer=_Proposer(exc=RuntimeError("llm down")))
    with pytest.raises(RuntimeError):
        await _run(clf)
