"""주제 제안(LLM)·주제용 판정자 문구 (module-4b)."""
from __future__ import annotations

import dataclasses
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.graph_rag.extraction import Mention
from src.domain.graph_rag.resolution import Candidate
from src.domain.graph_rag.value_objects import GraphRagSettings
from src.domain.judgment.value_objects import (
    ChoiceAnswer,
    JudgmentBackendKind,
    JudgmentResponse,
)
from src.infrastructure.graph_rag.resolution.jev_chooser import JevEntityChooser
from src.infrastructure.graph_rag.resolution.llm_chooser import (
    EntityChoiceOutput,
    LlmEntityChooser,
)
from src.infrastructure.graph_rag.topic.prompts import (
    JEV_TOPIC_INSTRUCTIONS,
    JEV_TOPIC_NEW,
    JEV_TOPIC_QID,
    LLM_TOPIC_NEW_HINT,
    LLM_TOPIC_SYSTEM,
)
from src.infrastructure.graph_rag.topic.proposer import (
    LlmTopicProposer,
    TopicProposalOutput,
)

from tests.application.graph_rag.fakes import FakeReader

_M = Mention("여신", "주제:대분류", "대출 업무", "__document__")
_CANDS = {"C1": Candidate("t1", "대출", "주제:대분류", "", (), "topic", 1.0)}


def _llm_stack(output):
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=output)
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    factory = MagicMock()
    factory.create.return_value = llm
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=object())
    return structured, factory, repo


@pytest.mark.asyncio
async def test_proposer_maps_output_and_uses_extraction_model():
    structured, factory, repo = _llm_stack(TopicProposalOutput.model_validate({
        "major": {"name": " 여신 ", "description": "대출 업무"},
        "minor": {"name": "기업여신", "description": "법인 대출"},
        "secondary": ["고객", " ", "리스크", "인사", "총무"],
    }))
    settings = dataclasses.replace(GraphRagSettings.defaults(),
                                   extraction_llm_model_id="m-ext")
    proposal = await LlmTopicProposer(repo, factory, FakeReader(settings),
                                      MagicMock()).propose("문서 본문", "r")
    assert (proposal.major.name, proposal.major.description) == ("여신", "대출 업무")
    assert proposal.minor.name == "기업여신"
    assert proposal.secondary == ("고객", "리스크", "인사")
    assert repo.find_by_id.call_args.args[0] == "m-ext"
    assert "문서 본문" in str(structured.ainvoke.call_args.args[0])


@pytest.mark.asyncio
async def test_proposer_empty_minor_becomes_none():
    _, factory, repo = _llm_stack(TopicProposalOutput.model_validate({
        "major": {"name": "총무"}, "minor": {"name": "  "}, "secondary": [],
    }))
    settings = dataclasses.replace(GraphRagSettings.defaults(),
                                   extraction_llm_model_id="m")
    proposal = await LlmTopicProposer(repo, factory, FakeReader(settings),
                                      MagicMock()).propose("x", "r")
    assert proposal.minor is None and proposal.secondary == ()


@pytest.mark.asyncio
async def test_proposer_without_model_raises():
    _, factory, repo = _llm_stack(None)
    with pytest.raises(ValueError):
        await LlmTopicProposer(repo, factory, FakeReader(GraphRagSettings.defaults()),
                               MagicMock()).propose("x", "r")


@pytest.mark.asyncio
async def test_jev_chooser_uses_topic_question_text():
    port = MagicMock()
    port.judge = AsyncMock(return_value=JudgmentResponse(
        answers={JEV_TOPIC_QID: ChoiceAnswer(
            choice="C1", probabilities={"C1": 0.9, "NEW": 0.1}, confidence=0.9)},
        model="jev-latest", backend=JudgmentBackendKind.JEV, latency_ms=12,
    ))
    chooser = JevEntityChooser(port, timeout_seconds=3.0, qid=JEV_TOPIC_QID,
                               instructions=JEV_TOPIC_INSTRUCTIONS,
                               new_description=JEV_TOPIC_NEW)
    verdict = await chooser.choose(_M, "문서", _CANDS, "r")
    q = port.judge.call_args.args[0].questions[JEV_TOPIC_QID]
    assert q.instructions == JEV_TOPIC_INSTRUCTIONS
    assert q.criteria[-1] == ("NEW", JEV_TOPIC_NEW)
    assert verdict.label == "C1" and verdict.probabilities["C1"] == 0.9


@pytest.mark.asyncio
async def test_llm_chooser_uses_topic_system_text():
    structured, factory, repo = _llm_stack(
        EntityChoiceOutput(label="C1", confidence="high", reason="같은 영역"))
    settings = dataclasses.replace(GraphRagSettings.defaults(),
                                   extraction_llm_model_id="m")
    chooser = LlmEntityChooser(repo, factory, FakeReader(settings), MagicMock(),
                               system=LLM_TOPIC_SYSTEM, new_hint=LLM_TOPIC_NEW_HINT)
    await chooser.choose(_M, "문서", _CANDS, "r")
    messages = structured.ainvoke.call_args.args[0]
    assert messages[0] == ("system", LLM_TOPIC_SYSTEM)
    assert LLM_TOPIC_NEW_HINT in messages[1][1] and "대출 업무" in messages[1][1]
