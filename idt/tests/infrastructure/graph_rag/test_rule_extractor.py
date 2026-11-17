"""규칙 추출기 — 조문 참조 (Plan FR-05, LLM 호출 없음)."""
import pytest
from src.domain.graph_rag.extraction import REL_REFERS_TO, ChunkUnit, ExtractionContext
from src.infrastructure.graph_rag.extract.rule_extractor import RuleGraphExtractor

_CTX = ExtractionContext(
    model_id="m", entity_types=("조문", "기타"), relation_types=("참조", "기타"),
    request_id="r",
)


def _unit(text: str) -> ChunkUnit:
    return ChunkUnit(chunk_id="p1", document_id="doc-1", kb_id="kb", collection_name="c",
                     content=text, chunk_index=0)


@pytest.mark.asyncio
async def test_own_clause_refers_to_other_clauses():
    text = "제5조(대출한도) ① 제3조에 따른 대상자는 제7조의2 및 별표 1의 한도를 따른다."
    r = await RuleGraphExtractor().extract(_unit(text), _CTX)
    names = {m.name for m in r.mentions}
    assert names == {"제5조", "제3조", "제7조의2", "별표 1"}
    assert all(m.type == "조문" for m in r.mentions)
    # 조문 키는 문서 단위 — 다른 문서의 같은 조문 번호와 섞이지 않는다
    assert {m.key for m in r.mentions} == {
        "doc-1::제5조", "doc-1::제3조", "doc-1::제7조의2", "doc-1::별표 1",
    }
    targets = {rel.target for rel in r.relations}
    assert targets == {"doc-1::제3조", "doc-1::제7조의2", "doc-1::별표 1"}
    assert all(rel.source == "doc-1::제5조" for rel in r.relations)
    assert all(rel.kind == REL_REFERS_TO and rel.type == "참조" for rel in r.relations)
    assert all(rel.evidence for rel in r.relations)
    assert r.llm_calls == 0


@pytest.mark.asyncio
async def test_without_own_clause_only_mentions():
    r = await RuleGraphExtractor().extract(_unit("상품 설명. 자세한 내용은 제12조 참조"), _CTX)
    assert [m.name for m in r.mentions] == ["제12조"]
    assert r.relations == ()


@pytest.mark.asyncio
async def test_spacing_variants_and_self_reference_ignored():
    r = await RuleGraphExtractor().extract(
        _unit("제 5 조 (목적) 이 규정은 제5조 의 2 와 제 5 조를 따른다. 부칙 참조"), _CTX
    )
    names = {m.name for m in r.mentions}
    assert names == {"제5조", "제5조의2", "부칙"}
    assert {rel.target for rel in r.relations} == {"doc-1::제5조의2", "doc-1::부칙"}


@pytest.mark.asyncio
async def test_no_clause_text_returns_empty():
    r = await RuleGraphExtractor().extract(_unit("일반 설명 문장입니다."), _CTX)
    assert r.mentions == () and r.relations == ()
