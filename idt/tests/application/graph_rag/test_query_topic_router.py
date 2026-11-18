"""QueryTopicRouter — 질문 주제 판정 Jev → LLM (Design §11.9 질문 주제, FR-29)."""
from __future__ import annotations

import dataclasses
from unittest.mock import MagicMock

import pytest

from src.application.graph_rag.retrieval.router import QueryTopicRouter
from src.domain.graph_rag.interfaces import EntityChooserPort
from src.domain.graph_rag.resolution import ChooserVerdict, LlmConfidence
from src.domain.graph_rag.topic import Topic, TopicLevel, TopicOrigin, TopicStatus
from src.domain.graph_rag.value_objects import GraphRagSettings

from tests.application.graph_rag.fakes import FakeTopics


class _Chooser(EntityChooserPort):
    def __init__(self, verdicts=(), exc=None):
        self.verdicts, self.exc, self.calls = list(verdicts), exc, []

    async def choose(self, mention, context, candidates, request_id):
        self.calls.append((mention, dict(candidates)))
        if self.exc:
            raise self.exc
        return self.verdicts.pop(0)


def _topics(*names, minor_of=None):
    out = [Topic(f"t-{n}", n, n, TopicLevel.MAJOR, None, f"{n} 업무",
                 TopicStatus.ACTIVE, TopicOrigin.ADMIN) for n in names]
    out.append(Topic("t-minor", "세부", "세부", TopicLevel.MINOR, out[0].id, "",
                     TopicStatus.ACTIVE, TopicOrigin.ADMIN))
    return out


def _settings(**over):
    base = dataclasses.replace(GraphRagSettings.defaults(), jev_enabled=True)
    return dataclasses.replace(base, **over)


def _router(topics, jev=None, llm=None):
    return QueryTopicRouter(topics=FakeTopics(topics), jev_chooser=jev,
                            llm_chooser=llm or _Chooser(), logger=MagicMock())


@pytest.mark.asyncio
async def test_jev_confident_choice_scopes_to_major_only():
    jev = _Chooser([ChooserVerdict("C1", probabilities={"C1": 0.9, "C2": 0.05,
                                                         "NEW": 0.05})])
    r = _router(_topics("여신", "총무"), jev=jev)
    scope = await r.route("운전자금대출 한도는?", _settings(), "r")
    assert scope.topic_ids == ("t-여신",) and scope.decided_by == "jev"
    mention, candidates = jev.calls[0]
    assert mention.name == "운전자금대출 한도는?"
    assert [c.entity_id for c in candidates.values()] == ["t-여신", "t-총무"]


@pytest.mark.asyncio
async def test_jev_unsure_falls_to_llm():
    jev = _Chooser([ChooserVerdict("C1", probabilities={"C1": 0.5, "NEW": 0.5})])
    llm = _Chooser([ChooserVerdict("C2", confidence=LlmConfidence.MEDIUM)])
    scope = await _router(_topics("여신", "총무"), jev=jev, llm=llm).route(
        "회의실 예약", _settings(), "r")
    assert scope.topic_ids == ("t-총무",) and scope.decided_by == "llm"


@pytest.mark.asyncio
async def test_jev_off_uses_llm_and_low_confidence_means_no_scope():
    jev = _Chooser()
    llm = _Chooser([ChooserVerdict("C1", confidence=LlmConfidence.LOW)])
    scope = await _router(_topics("여신"), jev=jev, llm=llm).route(
        "질문", _settings(jev_enabled=False), "r")
    assert jev.calls == [] and scope.topic_ids is None
    assert scope.reason == "llm_unsure"


@pytest.mark.asyncio
async def test_llm_new_means_no_scope_and_no_topic_created():
    topics = _topics("여신")
    llm = _Chooser([ChooserVerdict("NEW", confidence=LlmConfidence.HIGH)])
    r = _router(topics, llm=llm)
    scope = await r.route("점심 메뉴", _settings(jev_enabled=False), "r")
    assert scope.topic_ids is None and scope.reason == "no_matching_topic"
    assert len(r._topics.rows) == len(topics)


@pytest.mark.asyncio
async def test_failures_mean_no_scope():
    r = _router(_topics("여신"), jev=_Chooser(exc=TimeoutError()),
                llm=_Chooser(exc=RuntimeError("down")))
    scope = await r.route("질문", _settings(), "r")
    assert scope.topic_ids is None and scope.reason == "llm_error"


@pytest.mark.asyncio
async def test_no_topics_skips_judging():
    llm = _Chooser()
    scope = await _router([], llm=llm).route("질문", _settings(), "r")
    assert scope.topic_ids is None and scope.reason == "no_topics" and llm.calls == []


@pytest.mark.asyncio
async def test_same_question_uses_cache():
    llm = _Chooser([ChooserVerdict("C1", confidence=LlmConfidence.HIGH)])
    r = _router(_topics("여신"), llm=llm)
    s = _settings(jev_enabled=False)
    first = await r.route("운전자금대출  한도", s, "r")
    second = await r.route("운전자금대출 한도", s, "r")  # 공백 차이는 같은 질문
    assert len(llm.calls) == 1
    assert second.topic_ids == first.topic_ids and second.decided_by == "cache"
