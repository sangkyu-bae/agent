"""판정 확장 미니 벤치 — answer-citation-verification Design §8.3 (실 LLM, -m llm).

1) 인용 확장 체인이 근거 판정에 새 오판을 만들지 않는가 (SC-10)
   — 확장 후 정상 문장 오판 ⊆ 확장 전 오판, 날조 3/3 검출 유지.
   기존 판정기(gpt-4o)는 말을 바꾼 정상 문장을 근거 없음으로 잡는 성향이 있어
   (2026-11-21 측정 4/7, 두 번 돌려도 같음) 확장 전 오판 수는 기록만 한다.
2) 올바른 인용 10쌍: supported 9/10 이상, 근거 문장 실재 9/10 이상 (SC-2 대리 지표)
3) 틀린 인용 5쌍(번호 뒤바꿈 4 + 값 변조 1): 최종 정책 기준 5/5 탈락 (SC-3)
실행: `python -m pytest <이 파일> -m llm -s`
청크는 사실관계가 분명한 가상 정책 문구다(실제 문서 문장을 싣지 않는다).
"""

from __future__ import annotations

import pytest
from langchain_openai import ChatOpenAI
from src.config import settings
from src.domain.answer_citation.models import RegisteredChunk
from src.domain.answer_citation.policy import CitationFinalizePolicy, EvidenceLocator
from src.domain.hallucination.citation_check import CitationCheckRequest, CitationPair
from src.infrastructure.hallucination.adapter import HallucinationEvaluatorAdapter

pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(not settings.openai_api_key, reason="OPENAI_API_KEY 없음"),
]

CHUNKS = {
    1: "가계대출 총량 관리: 2026년 가계대출 증가율 목표는 경상성장률 이내인 연 3.8%로 "
    "관리한다. 은행권은 분기별 목표치를 금융당국에 제출해야 한다.",
    2: "수도권 주택담보대출 한도는 차주당 최대 6억 원으로 제한한다. 다주택자는 수도권 "
    "주택 구입 목적의 주택담보대출을 받을 수 없다.",
    3: "수도권 주택담보대출의 만기는 최장 30년으로 제한한다. 기존 40년 만기 상품은 "
    "신규 취급을 중단한다.",
    4: "정책대출(디딤돌·버팀목) 공급 계획은 연간 계획 대비 25% 감축한다. 단, 신혼부부 "
    "특례 대출은 현행대로 유지한다.",
    5: "전세대출 보증비율은 수도권에 한해 현행 100%에서 90%로 낮춘다. 시행일은 "
    "2026년 7월 1일이다.",
}
SOURCES = "[수집된 검색 결과]\n" + "\n\n---\n\n".join(
    f"[출처 {n}: 가계부채 관리방안.pdf]\n{t}" for n, t in CHUNKS.items()
)
QUESTION = "가계부채 관리방안의 주요 내용을 알려 주세요."
REGISTERED = {
    n: RegisteredChunk(marker=n, chunk_id=f"ch-{n}", document_id="d", page=None, text=t)
    for n, t in CHUNKS.items()
}

CORRECT = [
    (1, "올해 가계대출 증가율은 경상성장률 이내인 3.8%로 관리됩니다."),
    (1, "은행은 분기마다 목표치를 금융당국에 제출해야 합니다."),
    (2, "수도권 주담대 한도는 차주 1인당 6억 원까지입니다."),
    (2, "다주택자는 수도권 집을 사기 위한 주담대를 받을 수 없습니다."),
    (3, "수도권 주담대 만기는 최대 30년입니다."),
    (3, "40년 만기 상품은 새로 판매되지 않습니다."),
    (4, "디딤돌·버팀목 정책대출 공급은 계획 대비 25% 줄어듭니다."),
    (4, "신혼부부 특례 대출은 그대로 유지됩니다."),
    (5, "수도권 전세대출 보증비율은 90%로 낮아집니다."),
    (5, "전세대출 보증비율 변경은 2026년 7월 1일부터 시행됩니다."),
]
WRONG = [
    (3, "수도권 주담대 한도는 차주 1인당 6억 원까지입니다."),
    (2, "수도권 주담대 만기는 최대 30년입니다."),
    (5, "디딤돌·버팀목 정책대출 공급은 계획 대비 25% 줄어듭니다."),
    (1, "수도권 전세대출 보증비율은 90%로 낮아집니다."),
    (2, "수도권 주담대 한도는 차주 1인당 8억 원까지입니다."),
]
# (문장, 올바른 인용 번호들)
NORMAL = [
    ("올해 가계대출 증가율은 3.8% 이내로 관리됩니다.", (1,)),
    ("수도권 주담대 한도는 6억 원이고 만기는 최장 30년입니다.", (2, 3)),
    ("다주택자는 수도권 주택 구입용 주담대를 받을 수 없습니다.", (2,)),
    ("정책대출은 25% 줄지만 신혼부부 특례는 유지됩니다.", (4,)),
    ("수도권 전세대출 보증비율은 2026년 7월 1일부터 90%가 됩니다.", (5,)),
    (
        "은행은 분기별 목표치를 제출합니다. 자세한 내용은 거래 은행에 문의해 주세요.",
        (1,),
    ),
    ("40년 만기 주담대는 신규 취급이 중단됩니다.", (3,)),
]
FABRICATED = [
    (
        "수도권 주담대 한도는 6억 원입니다. "
        "자세한 상담은 대표번호 1588-1234로 문의하세요.",
        "1588-1234",
    ),
    ("수도권 주담대 한도는 8억 원입니다.", "8억"),
    ("수도권 주담대 만기는 최장 50년까지 가능합니다.", "50년"),
]


class _Provider:
    def __init__(self) -> None:
        self._llm = ChatOpenAI(
            model=settings.grounding_judge_model or "gpt-4o",
            temperature=0.0,
            api_key=settings.openai_api_key,
        )

    async def get(self, temperature: float = 0.0):
        return self._llm

    async def invalidate(self) -> None:
        return None


@pytest.fixture(scope="module")
def adapter() -> HallucinationEvaluatorAdapter:
    return HallucinationEvaluatorAdapter(llm_provider=_Provider())


def _request(pairs: list[tuple[int, str]]) -> CitationCheckRequest:
    return CitationCheckRequest(
        pairs=tuple(CitationPair(f"c{i + 1}", m, s) for i, (m, s) in enumerate(pairs)),
        cited_sources={m: CHUNKS[m] for m, _ in pairs},
    )


def _generation(pairs: list[tuple[int, str]]) -> str:
    return " ".join(s[:-1] + f"[{m}]." for m, s in pairs)


async def _judge(adapter, generation: str, citations=None):
    return await adapter.judge(
        question=QUESTION,
        sources=SOURCES,
        generation=generation,
        hints=[],
        request_id="bench",
        citations=citations,
    )


async def _detected(adapter, generation: str, citations=None) -> list[str]:
    verdict = (await _judge(adapter, generation, citations)).excluding_found_in(SOURCES)
    return [c.span for c in verdict.high_claims]


@pytest.mark.asyncio
async def test_citation_chain_adds_no_new_grounding_false_positive(adapter):
    rows = []
    for text, markers in NORMAL:
        base = await _detected(adapter, text)
        ext = await _detected(adapter, text, _request([(m, text) for m in markers]))
        rows.append(("normal", bool(base), bool(ext)))
    for text, value in FABRICATED:
        base = await _detected(adapter, text)
        ext = await _detected(adapter, text, _request([(2, text)]))
        rows.append(
            ("fabricated", any(value in s for s in base), any(value in s for s in ext))
        )
    normal = [r for r in rows if r[0] == "normal"]
    print("\n[bench] grounding (kind, base_flag, ext_flag):", rows)
    print(
        f"[bench] normal false positive base {sum(r[1] for r in normal)}/7, "
        f"ext {sum(r[2] for r in normal)}/7"
    )
    assert not [r for r in normal if r[2] and not r[1]], (
        "확장 체인이 새 오판을 만들었다"
    )
    assert all(r[1] and r[2] for r in rows if r[0] == "fabricated"), "날조 미검출"


@pytest.mark.asyncio
async def test_correct_citations_supported_with_evidence(adapter):
    verdict = await _judge(adapter, _generation(CORRECT), _request(CORRECT))
    by_id = {c.pair_id: c for c in verdict.citation_checks}
    checks = [by_id.get(f"c{i + 1}") for i in range(len(CORRECT))]
    ok = sum(1 for c in checks if c and c.supported)
    found = sum(
        1
        for (m, _), c in zip(CORRECT, checks)
        if c and c.supported and EvidenceLocator.find(c.evidence, CHUNKS[m])
    )
    print(f"\n[bench] correct supported {ok}/10, evidence found {found}/10")
    assert ok >= 9 and found >= 9


@pytest.mark.asyncio
async def test_wrong_citations_rejected_after_policy(adapter):
    """판정기 응답 + 결정적 정리 정책을 거친 최종 결과로 센다(화면에 남는가)."""
    request = _request(WRONG)
    verdict = await _judge(adapter, _generation(WRONG), request)
    by_id = {c.pair_id: c for c in verdict.citation_checks}
    raw_supported = sum(1 for c in verdict.citation_checks if c.supported)
    kept = 0
    for pair in request.pairs:  # 쌍마다 따로 정리해 남는지 본다
        check = by_id.get(pair.pair_id)
        out = CitationFinalizePolicy.finalize(
            pair.sentence[:-1] + f"[{pair.marker}].",
            chunks=REGISTERED,
            pairs=(pair,),
            checks=(check,) if check else (),
            judged=True,
        )
        kept += out.status == "verified"
    print(
        f"\n[bench] wrong raw supported {raw_supported}/5, kept after policy {kept}/5"
    )
    assert kept == 0
