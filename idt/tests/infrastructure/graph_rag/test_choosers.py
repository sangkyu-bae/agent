"""엔티티 판정자 — Jev ChoiceQuestion / LLM 구조화 출력 / 이름 임베더 (Design §2.2 판정)."""
from __future__ import annotations

import dataclasses
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.domain.graph_rag.extraction import Mention
from src.domain.graph_rag.resolution import NEW_LABEL, Candidate, LlmConfidence
from src.domain.graph_rag.value_objects import GraphRagSettings
from src.domain.judgment.interfaces import JudgmentPort
from src.domain.judgment.value_objects import (
    ChoiceAnswer,
    ChoiceQuestion,
    JudgmentBackendKind,
    JudgmentResponse,
)
from src.infrastructure.graph_rag.resolution.jev_chooser import (
    QID,
    JevEntityChooser,
)
from src.infrastructure.graph_rag.resolution.llm_chooser import (
    EntityChoiceOutput,
    LlmEntityChooser,
)

from tests.application.graph_rag.fakes import FakeReader

_M = Mention(name="A 상품", type="상품", description="대출 상품", chunk_id="p1")
_CANDS = {
    "C1": Candidate("e1", "A상품", "상품", "기업 운전자금 대출", (), "vector", 0.92),
    "C2": Candidate("e2", "B상품", "상품", "", (), "vector", 0.80),
}


class _Port(JudgmentPort):
    kind = JudgmentBackendKind.JEV

    def __init__(self):
        self.requests = []

    async def judge(self, request):
        self.requests.append(request)
        return JudgmentResponse(
            answers={QID: ChoiceAnswer(
                choice="C1", probabilities={"C1": 0.7, "C2": 0.1, NEW_LABEL: 0.2},
                confidence=0.7,
            )},
            model="jev-latest", backend=JudgmentBackendKind.JEV, latency_ms=12,
        )


@pytest.mark.asyncio
async def test_jev_chooser_builds_choice_question_and_returns_probabilities():
    port = _Port()
    verdict = await JevEntityChooser(port, timeout_seconds=3.0).choose(
        _M, "A 상품은 기업 대상 대출이다.", _CANDS, "r"
    )
    assert verdict.label == "C1"
    assert verdict.probabilities == {"C1": 0.7, "C2": 0.1, NEW_LABEL: 0.2}
    (req,) = port.requests
    q = req.questions[QID]
    assert isinstance(q, ChoiceQuestion)
    assert q.labels == ("C1", "C2", NEW_LABEL)
    assert "A상품" in dict(q.criteria)["C1"]
    assert req.state["mention"] == "A 상품" and "기업 대상" in req.state["context"]


@pytest.mark.asyncio
async def test_llm_chooser_maps_output_and_uses_rejudge_model():
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=EntityChoiceOutput(
        label="C2", confidence="medium", reason="표기만 다름"
    ))
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    factory = MagicMock()
    factory.create.return_value = llm
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=object())
    settings = dataclasses.replace(
        GraphRagSettings.defaults(), extraction_llm_model_id="m-ext",
        rejudge_llm_model_id="m-rejudge",
    )
    chooser = LlmEntityChooser(repo, factory, FakeReader(settings), MagicMock())
    verdict = await chooser.choose(_M, "문맥", _CANDS, "r")
    assert verdict.label == "C2" and verdict.confidence is LlmConfidence.MEDIUM
    assert verdict.reason == "표기만 다름"
    assert repo.find_by_id.call_args.args[0] == "m-rejudge"
    prompt = str(structured.ainvoke.call_args.args[0])
    assert "C1" in prompt and "A상품" in prompt and NEW_LABEL in prompt


@pytest.mark.asyncio
async def test_llm_chooser_unknown_label_becomes_new_low():
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=EntityChoiceOutput(
        label="C9", confidence="high", reason=""
    ))
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    factory = MagicMock()
    factory.create.return_value = llm
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=object())
    settings = dataclasses.replace(GraphRagSettings.defaults(),
                                   extraction_llm_model_id="m")
    verdict = await LlmEntityChooser(repo, factory, FakeReader(settings),
                                     MagicMock()).choose(_M, "", _CANDS, "r")
    assert verdict.label == NEW_LABEL and verdict.confidence is LlmConfidence.LOW


def test_embedder_requests_configured_dimensions(monkeypatch):
    import src.infrastructure.graph_rag.resolution.embedder as mod

    captured = {}

    class _FakeOpenAIEmbeddings:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(mod, "OpenAIEmbeddings", _FakeOpenAIEmbeddings)
    mod.OpenAIEntityEmbedder("text-embedding-3-small", 512, api_key="k")
    assert captured["dimensions"] == 512
    assert captured["model"] == "text-embedding-3-small"
