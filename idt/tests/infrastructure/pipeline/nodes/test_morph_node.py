from unittest.mock import MagicMock

import pytest
from langchain_core.documents import Document

from src.domain.morph.schemas import MorphAnalysisResult, MorphToken
from src.infrastructure.pipeline.nodes.morph_node import morph_node
from src.infrastructure.pipeline.state.advanced_pipeline_state import (
    create_advanced_initial_state,
)


def _make_state(**overrides):
    state = create_advanced_initial_state(
        file_bytes=b"pdf", filename="t.pdf", user_id="u", request_id="r",
    )
    state["chunked_documents"] = [
        Document(page_content="금융 시장의 동향 분석", metadata={}),
        Document(page_content="대출 금리가 상승했다", metadata={}),
    ]
    state.update(overrides)
    return state


def _make_morph_analyzer(tokens_per_call=None, side_effect=None):
    analyzer = MagicMock()
    if side_effect:
        analyzer.analyze.side_effect = side_effect
    elif tokens_per_call:
        analyzer.analyze.side_effect = tokens_per_call
    else:
        analyzer.analyze.return_value = MorphAnalysisResult(
            tokens=(
                MorphToken(surface="금융", pos="NNG", start=0, length=2),
                MorphToken(surface="시장", pos="NNG", start=3, length=2),
                MorphToken(surface="의", pos="JKG", start=5, length=1),
                MorphToken(surface="동향", pos="NNG", start=7, length=2),
                MorphToken(surface="분석", pos="NNG", start=10, length=2),
            ),
            text="금융 시장의 동향 분석",
        )
    return analyzer


class TestMorphNode:

    @pytest.mark.asyncio
    async def test_happy_path(self):
        state = _make_state()
        analyzer = _make_morph_analyzer()

        result = await morph_node(state, analyzer)

        assert result["morph_applied"] is True
        assert len(result["morph_keywords_per_chunk"]) == 2
        assert analyzer.analyze.call_count == 2

    @pytest.mark.asyncio
    async def test_keywords_contain_nouns(self):
        state = create_advanced_initial_state(
            file_bytes=b"x", filename="a.pdf", user_id="u", request_id="r",
        )
        state["chunked_documents"] = [
            Document(page_content="금융 시장", metadata={}),
        ]
        analyzer = _make_morph_analyzer()

        result = await morph_node(state, analyzer)

        keywords = result["morph_keywords_per_chunk"][0]
        assert "금융" in keywords
        assert "시장" in keywords

    @pytest.mark.asyncio
    async def test_verb_gets_da_suffix(self):
        state = create_advanced_initial_state(
            file_bytes=b"x", filename="a.pdf", user_id="u", request_id="r",
        )
        state["chunked_documents"] = [
            Document(page_content="상승했다", metadata={}),
        ]
        analyzer = MagicMock()
        analyzer.analyze.return_value = MorphAnalysisResult(
            tokens=(
                MorphToken(surface="상승", pos="VV", start=0, length=2),
            ),
            text="상승했다",
        )

        result = await morph_node(state, analyzer)

        assert "상승다" in result["morph_keywords_per_chunk"][0]

    @pytest.mark.asyncio
    async def test_sets_metadata_on_chunks(self):
        state = _make_state()
        analyzer = _make_morph_analyzer()

        result = await morph_node(state, analyzer)

        for chunk in state["chunked_documents"]:
            assert "morph_keywords" in chunk.metadata

    @pytest.mark.asyncio
    async def test_empty_chunks(self):
        state = _make_state(chunked_documents=[])
        analyzer = _make_morph_analyzer()

        result = await morph_node(state, analyzer)

        assert result["morph_applied"] is False
        assert result["morph_keywords_per_chunk"] == []

    @pytest.mark.asyncio
    async def test_exception_graceful(self):
        state = _make_state()
        analyzer = _make_morph_analyzer(side_effect=RuntimeError("kiwi error"))

        result = await morph_node(state, analyzer)

        assert result["morph_applied"] is False
        assert any("Morph analysis failed" in e for e in result["errors"])
