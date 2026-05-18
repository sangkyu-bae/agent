from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from src.domain.parser.parse_quality import ParseQualityScore
from src.infrastructure.pipeline.nodes.layout_analyze_node import layout_analyze_node
from src.infrastructure.pipeline.state.advanced_pipeline_state import (
    create_advanced_initial_state,
)


def _make_state(**overrides):
    state = create_advanced_initial_state(
        file_bytes=b"pdf-content", filename="doc.pdf",
        user_id="u1", request_id="r1",
    )
    state["parsed_documents"] = [
        Document(page_content="original", metadata={"page": 1}),
    ]
    state["document_type"] = "text_heavy"
    state.update(overrides)
    return state


def _make_quality(score=0.85):
    return ParseQualityScore(
        page=1, score=score, text_char_count=100,
        avg_word_length=4.5, order_consistency=0.9, issues=(),
    )


class TestLayoutAnalyzeNode:

    @pytest.mark.asyncio
    @patch("src.infrastructure.pipeline.nodes.layout_analyze_node.fitz")
    async def test_happy_path(self, mock_fitz):
        mock_pdf_doc = MagicMock()
        mock_fitz.open.return_value = mock_pdf_doc

        state = _make_state()
        analyzer = MagicMock()
        docs = [Document(page_content="layout result", metadata={})]
        analyzer.analyze.return_value = (docs, _make_quality(0.85))

        result = await layout_analyze_node(state, analyzer)

        assert result["layout_applied"] is True
        assert result["layout_quality_score"] == 0.85
        assert len(result["parsed_documents"]) == 1
        mock_pdf_doc.close.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.infrastructure.pipeline.nodes.layout_analyze_node.fitz")
    async def test_quality_below_threshold_skips(self, mock_fitz):
        mock_fitz.open.return_value = MagicMock()

        state = _make_state()
        analyzer = MagicMock()
        analyzer.analyze.return_value = ([], _make_quality(0.5))

        result = await layout_analyze_node(state, analyzer)

        assert result["layout_applied"] is False
        assert result["layout_quality_score"] == 0.5
        assert "parsed_documents" not in result

    @pytest.mark.asyncio
    async def test_disabled_skips(self):
        state = _make_state(enable_layout_analysis=False)
        analyzer = MagicMock()

        result = await layout_analyze_node(state, analyzer)

        assert result["layout_applied"] is False
        assert result["layout_quality_score"] is None
        analyzer.analyze.assert_not_called()

    @pytest.mark.asyncio
    async def test_ocr_heavy_skips(self):
        state = _make_state(document_type="ocr_heavy")
        analyzer = MagicMock()

        result = await layout_analyze_node(state, analyzer)

        assert result["layout_applied"] is False
        analyzer.analyze.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.infrastructure.pipeline.nodes.layout_analyze_node.fitz")
    async def test_exception_returns_graceful_failure(self, mock_fitz):
        mock_fitz.open.side_effect = RuntimeError("fitz error")

        state = _make_state()
        analyzer = MagicMock()

        result = await layout_analyze_node(state, analyzer)

        assert result["layout_applied"] is False
        assert result["layout_quality_score"] is None
        assert any("Layout analysis failed" in e for e in result["errors"])
