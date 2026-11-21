"""GroundedGenerator 인용 검증 S7 — answer-citation-verification D-05·D-06."""

from unittest.mock import MagicMock

import pytest
from src.application.hallucination.grounded_generation import GroundedGenerator
from src.domain.hallucination.citation_check import (
    CitationCheck,
    CitationCheckRequest,
    CitationPair,
)
from src.domain.hallucination.grounding import (
    GroundingJudgePort,
    GroundingVerdict,
    UnsupportedClaim,
)

SOURCES = "[출처 1: a.pdf]\n근거 본문"


def _req(text: str) -> CitationCheckRequest:
    return CitationCheckRequest(
        pairs=(CitationPair("c1", 1, text),), cited_sources={1: "근거"}
    )


def _verdict(*spans, checks=()):
    return GroundingVerdict(
        unsupported_claims=tuple(
            UnsupportedClaim(s, "근거 없음", "high") for s in spans
        ),
        citation_checks=tuple(checks),
    )


class FakeJudge(GroundingJudgePort):
    def __init__(self, verdicts=None, raises=None):
        self.verdicts = list(verdicts or [])
        self.raises = raises
        self.calls: list[dict] = []

    async def judge(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
            raise self.raises
        return self.verdicts.pop(0) if self.verdicts else _verdict()


def _gen(outputs):
    queue = list(outputs)

    async def generate(feedback: str) -> str:
        return queue.pop(0)

    return generate


def _grounded(judge, enabled=True):
    return GroundedGenerator(
        judge, MagicMock(), enabled=enabled, corpus_max_chars=24000
    )


@pytest.mark.asyncio
async def test_without_citations_judge_kwargs_are_unchanged():
    judge = FakeJudge([_verdict()])
    await _grounded(judge).run(
        generate=_gen(["답"]),
        question="Q",
        sources=SOURCES,
        max_retries=1,
        target="answer",
        request_id="r",
    )
    assert "citations" not in judge.calls[0]


@pytest.mark.asyncio
async def test_request_is_built_per_text_and_last_verdict_returned():
    checks = (CitationCheck("c1", True, "근거"),)
    judge = FakeJudge([_verdict("X"), _verdict(checks=checks)])
    result = await _grounded(judge).run(
        generate=_gen(["첫 답 X", "고친 답"]),
        question="Q",
        sources=SOURCES,
        max_retries=1,
        target="answer",
        request_id="r",
        citations=_req,
    )
    assert [c["citations"].pairs[0].sentence for c in judge.calls] == [
        "첫 답 X",
        "고친 답",
    ]
    assert result.text == "고친 답"
    assert result.verdict.citation_checks == checks
    assert result.citation_request.pairs[0].sentence == "고친 답"


@pytest.mark.asyncio
async def test_builder_returning_none_sends_no_citations():
    judge = FakeJudge([_verdict()])
    result = await _grounded(judge).run(
        generate=_gen(["답"]),
        question="Q",
        sources=SOURCES,
        max_retries=1,
        target="answer",
        request_id="r",
        citations=lambda text: None,
    )
    assert "citations" not in judge.calls[0]
    assert result.citation_request is None
    assert result.verdict is not None


@pytest.mark.asyncio
async def test_judge_failure_leaves_no_verdict():
    result = await _grounded(FakeJudge(raises=RuntimeError("down"))).run(
        generate=_gen(["답"]),
        question="Q",
        sources=SOURCES,
        max_retries=1,
        target="answer",
        request_id="r",
        citations=_req,
    )
    assert result.verdict is None and result.citation_request is None


@pytest.mark.asyncio
async def test_verify_citations_single_call_even_when_disabled():
    checks = (CitationCheck("c1", True, "근거"),)
    judge = FakeJudge([_verdict("X", checks=checks)])
    grounded = _grounded(judge, enabled=False)
    verdict = await grounded.verify_citations(
        question="Q", sources=SOURCES, text="답", request=_req("답"), request_id="r"
    )
    assert len(judge.calls) == 1
    assert judge.calls[0]["citations"].pairs[0].sentence == "답"
    assert verdict.citation_checks == checks


@pytest.mark.asyncio
async def test_verify_citations_none_without_judge_or_request_or_on_failure():
    req = _req("답")
    assert (
        await GroundedGenerator(
            None, MagicMock(), enabled=True, corpus_max_chars=1
        ).verify_citations(
            question="Q", sources=SOURCES, text="답", request=req, request_id="r"
        )
        is None
    )
    assert (
        await _grounded(FakeJudge()).verify_citations(
            question="Q", sources=SOURCES, text="답", request=None, request_id="r"
        )
        is None
    )
    failing = _grounded(FakeJudge(raises=RuntimeError("down")))
    assert (
        await failing.verify_citations(
            question="Q", sources=SOURCES, text="답", request=req, request_id="r"
        )
        is None
    )
