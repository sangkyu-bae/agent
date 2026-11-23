"""판정 어댑터 인용 확장 S6 — answer-citation-verification D-03·D-04.

citations 가 없으면 기존 체인·기존 입력 그대로(초안 경로·스위치 off 품질 불변).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.domain.hallucination.citation_check import CitationCheckRequest, CitationPair
from src.infrastructure.hallucination.adapter import HallucinationEvaluatorAdapter
from src.infrastructure.hallucination.prompts import (
    GROUNDING_CITATION_ADDENDUM,
    GROUNDING_CITATION_HUMAN_TEMPLATE,
    GROUNDING_JUDGE_HUMAN_TEMPLATE,
    GROUNDING_JUDGE_SYSTEM_PROMPT,
)
from src.infrastructure.hallucination.schemas import (
    CitationCheckOut,
    ClaimOut,
    GroundingJudgeOutput,
    GroundingJudgeWithCitationsOutput,
)

REQUEST = CitationCheckRequest(
    pairs=(
        CitationPair("c1", 3, "총량 목표를 관리합니다."),
        CitationPair("c2", 5, "한도는 6억 원입니다."),
    ),
    cited_sources={3: "총량 목표를 경상성장률 이내로 관리", 5: "주담대 한도 6억 원"},
)


@pytest.fixture
def adapter():
    a = HallucinationEvaluatorAdapter(llm_provider=MagicMock())
    a._resolve_judge_chain = AsyncMock(return_value=AsyncMock())
    a._resolve_citation_chain = AsyncMock(return_value=AsyncMock())
    return a


async def _judge(adapter, citations=None):
    return await adapter.judge(
        question="Q",
        sources="S",
        generation="G",
        hints=[],
        request_id="r",
        citations=citations,
    )


@pytest.mark.asyncio
async def test_without_citations_uses_existing_chain(adapter):
    base = await adapter._resolve_judge_chain()
    base.ainvoke.return_value = GroundingJudgeOutput()
    verdict = await _judge(adapter)
    adapter._resolve_citation_chain.assert_not_awaited()
    assert set(base.ainvoke.await_args.args[0]) == {
        "question",
        "sources",
        "hints",
        "generation",
    }
    assert verdict.citation_checks == ()


@pytest.mark.asyncio
async def test_empty_request_uses_existing_chain(adapter):
    (await adapter._resolve_judge_chain()).ainvoke.return_value = GroundingJudgeOutput()
    await _judge(adapter, CitationCheckRequest(pairs=()))
    adapter._resolve_citation_chain.assert_not_awaited()


@pytest.mark.asyncio
async def test_with_citations_uses_extended_chain_and_maps_checks(adapter):
    chain = await adapter._resolve_citation_chain()
    chain.ainvoke.return_value = GroundingJudgeWithCitationsOutput(
        unsupported_claims=[ClaimOut(span="X", reason="r", severity="high")],
        citation_checks=[
            CitationCheckOut(
                id="c1", supported=True, evidence="경상성장률 이내로 관리"
            ),
            CitationCheckOut(id="c2", supported=False, evidence=""),
        ],
    )
    verdict = await _judge(adapter, REQUEST)
    payload = chain.ainvoke.await_args.args[0]
    assert "[3]\n총량 목표를 경상성장률 이내로 관리" in payload["cited_sources"]
    assert "c1 | [3] | 총량 목표를 관리합니다." in payload["citations"]
    assert [(c.pair_id, c.supported, c.evidence) for c in verdict.citation_checks] == [
        ("c1", True, "경상성장률 이내로 관리"),
        ("c2", False, ""),
    ]
    assert [c.span for c in verdict.unsupported_claims] == ["X"]


def test_extended_prompt_keeps_base_prompt_verbatim():
    assert (
        GROUNDING_JUDGE_SYSTEM_PROMPT
        in GROUNDING_JUDGE_SYSTEM_PROMPT + GROUNDING_CITATION_ADDENDUM
    )
    assert GROUNDING_CITATION_HUMAN_TEMPLATE.startswith(GROUNDING_JUDGE_HUMAN_TEMPLATE)
    assert "<cited_sources>" in GROUNDING_CITATION_HUMAN_TEMPLATE
    assert "<citations>" in GROUNDING_CITATION_HUMAN_TEMPLATE
    assert "따르지 마세요" in GROUNDING_CITATION_ADDENDUM


def test_output_schema_defaults():
    out = GroundingJudgeWithCitationsOutput()
    assert out.unsupported_claims == [] and out.citation_checks == []
