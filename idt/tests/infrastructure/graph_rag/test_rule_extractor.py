"""규칙 추출기 — 조문 제목·조문 참조 (Plan FR-05, LLM 호출 없음).

2026-11-17 실추출 반영: 청크가 "규정 (발췌)"처럼 제목 줄로 시작해도 줄 첫머리의
`제N조(제목)`을 모두 찾아 조문→제목 개념(정의) 관계를 만들고, 본문 속 참조는
그 문장이 속한 조문에서 나가는 REFERS_TO 로 만든다.
"""
import pytest
from src.domain.graph_rag.extraction import (
    REL_REFERS_TO,
    REL_RELATES,
    ChunkUnit,
    ExtractionContext,
)
from src.infrastructure.graph_rag.extract.rule_extractor import RuleGraphExtractor

_CTX = ExtractionContext(
    model_id="m", entity_types=("조문", "용어", "기타"),
    relation_types=("참조", "정의", "기타"), request_id="r",
)


def _unit(text: str) -> ChunkUnit:
    return ChunkUnit(chunk_id="p1", document_id="doc-1", kb_id="kb", collection_name="c",
                     content=text, chunk_index=0)


def _refers(r):
    return {(x.source, x.target) for x in r.relations if x.kind == REL_REFERS_TO}


def _titles(r):
    return {(x.source, x.target) for x in r.relations if x.kind == REL_RELATES}


@pytest.mark.asyncio
async def test_headings_after_preface_link_clause_to_title():
    text = (
        "여신 취급 규정 (발췌)\n"
        "제12조(운전자금대출 한도) 운전자금대출 한도는 연매출액의 30% 이내로 한다.\n"
        "제15조(적용 금리) 기준금리는 연 4.2%이며 제12조의 한도를 따른다.\n"
    )
    r = await RuleGraphExtractor().extract(_unit(text), _CTX)
    assert _titles(r) == {
        ("doc-1::제12조", "운전자금대출 한도"),
        ("doc-1::제15조", "적용 금리"),
    }
    title_rel = next(x for x in r.relations if x.target == "운전자금대출 한도")
    assert title_rel.type == "정의"
    assert title_rel.evidence == "제12조(운전자금대출 한도)"
    # 제15조 본문의 '제12조' 참조는 제15조에서 나간다
    assert _refers(r) == {("doc-1::제15조", "doc-1::제12조")}
    names = {(m.name, m.type) for m in r.mentions}
    assert {("제12조", "조문"), ("제15조", "조문")} <= names
    assert {("운전자금대출 한도", "용어"), ("적용 금리", "용어")} <= names
    assert r.llm_calls == 0


@pytest.mark.asyncio
async def test_clause_keys_are_document_scoped():
    r = await RuleGraphExtractor().extract(
        _unit("제5조(대출한도) ① 제3조에 따른 대상자는 제7조의2 및 별표 1의 한도를 따른다."),
        _CTX,
    )
    clause_keys = {m.key for m in r.mentions if m.type == "조문"}
    assert clause_keys == {
        "doc-1::제5조", "doc-1::제3조", "doc-1::제7조의2", "doc-1::별표 1",
    }
    assert _refers(r) == {
        ("doc-1::제5조", "doc-1::제3조"), ("doc-1::제5조", "doc-1::제7조의2"),
        ("doc-1::제5조", "doc-1::별표 1"),
    }
    assert all(x.type == "참조" and x.evidence for x in r.relations if x.kind == REL_REFERS_TO)


@pytest.mark.asyncio
async def test_inline_reference_with_parentheses_is_not_a_heading():
    # 줄 첫머리가 아닌 '제3조(정의)에 따른'은 제목이 아니라 참조
    r = await RuleGraphExtractor().extract(
        _unit("제5조(대상) 제3조(정의)에 따른 고객을 말한다."), _CTX
    )
    assert _titles(r) == {("doc-1::제5조", "대상")}
    assert _refers(r) == {("doc-1::제5조", "doc-1::제3조")}


@pytest.mark.asyncio
async def test_without_heading_only_mentions():
    r = await RuleGraphExtractor().extract(_unit("상품 설명. 자세한 내용은 제12조 참조"), _CTX)
    assert [m.name for m in r.mentions] == ["제12조"]
    assert r.relations == ()


@pytest.mark.asyncio
async def test_heading_without_title_still_owns_references():
    r = await RuleGraphExtractor().extract(
        _unit("제 5 조 이 규정은 제5조 의 2 와 제 5 조를 따른다. 부칙 참조"), _CTX
    )
    assert {m.name for m in r.mentions} == {"제5조", "제5조의2", "부칙"}
    assert _refers(r) == {("doc-1::제5조", "doc-1::제5조의2"), ("doc-1::제5조", "doc-1::부칙")}
    assert _titles(r) == set()


@pytest.mark.asyncio
async def test_no_clause_text_returns_empty():
    r = await RuleGraphExtractor().extract(_unit("일반 설명 문장입니다."), _CTX)
    assert r.mentions == () and r.relations == ()
