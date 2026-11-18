"""LLM 구조화 추출기 (Plan FR-06) — 타입 목록 밖은 '기타', 끝점 없는 관계는 버림."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.domain.graph_rag.extraction import ChunkUnit, ExtractionContext
from src.infrastructure.graph_rag.extract.llm_extractor import (
    GraphExtractionOutput,
    LlmGraphExtractor,
)

_CTX = ExtractionContext(
    model_id="m-1", entity_types=("상품·서비스", "대상", "기타"),
    relation_types=("적용대상", "기타"), request_id="r",
)
_UNIT = ChunkUnit(chunk_id="p1", document_id="d", kb_id="kb", collection_name="c",
                  content="A상품은 개인사업자를 대상으로 한다.", chunk_index=0)


def _extractor(output, *, model=object()):
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=output)
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    factory = MagicMock()
    factory.create.return_value = llm
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=model)
    return LlmGraphExtractor(repo, factory, MagicMock()), structured, factory


@pytest.mark.asyncio
async def test_maps_output_and_normalizes_types():
    out = GraphExtractionOutput.model_validate({
        "entities": [
            {"name": "A상품", "type": "상품·서비스", "description": "대출 상품"},
            {"name": "개인사업자", "type": "고객", "description": ""},  # 목록 밖
        ],
        "relations": [
            {"source": "A상품", "target": "개인사업자", "type": "적용대상",
             "evidence": "A상품은 개인사업자를 대상으로"},
            {"source": "A상품", "target": "없는엔티티", "type": "적용대상",
             "evidence": "x"},                               # 끝점 없음 → 버림
            {"source": "A상품", "target": "개인사업자", "type": "대출조건",
             "evidence": "A상품은"},                          # 목록 밖 → 기타
        ],
    })
    extractor, structured, _ = _extractor(out)
    r = await extractor.extract(_UNIT, _CTX)
    assert [(m.name, m.type) for m in r.mentions] == [
        ("A상품", "상품·서비스"), ("개인사업자", "기타"),
    ]
    assert [(x.target, x.type) for x in r.relations] == [
        ("개인사업자", "적용대상"), ("개인사업자", "기타"),
    ]
    assert all(m.chunk_id == "p1" for m in r.mentions)
    assert r.llm_calls == 1
    prompt = str(structured.ainvoke.call_args.args[0])
    assert "상품·서비스" in prompt and "A상품은 개인사업자를" in prompt


@pytest.mark.asyncio
async def test_llm_built_once_per_model():
    extractor, _, factory = _extractor(GraphExtractionOutput())
    await extractor.extract(_UNIT, _CTX)
    await extractor.extract(_UNIT, _CTX)
    assert factory.create.call_count == 1


@pytest.mark.asyncio
async def test_missing_model_raises():
    extractor, _, _ = _extractor(GraphExtractionOutput(), model=None)
    with pytest.raises(ValueError):
        await extractor.extract(_UNIT, _CTX)


@pytest.mark.asyncio
async def test_blank_names_dropped():
    out = GraphExtractionOutput.model_validate({
        "entities": [{"name": "  ", "type": "대상", "description": ""}],
        "relations": [],
    })
    extractor, _, _ = _extractor(out)
    r = await extractor.extract(_UNIT, _CTX)
    assert r.mentions == ()
