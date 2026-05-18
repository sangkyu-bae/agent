from unittest.mock import MagicMock

import pytest

from src.domain.pdf_analyzer.schemas import (
    AnalysisResult,
    PDFDocumentType,
    PageFeatures,
    SummaryMetrics,
)
from src.infrastructure.pipeline.nodes.analyze_node import analyze_node
from src.infrastructure.pipeline.state.advanced_pipeline_state import (
    create_advanced_initial_state,
)


def _make_analysis_result(
    doc_type: PDFDocumentType = PDFDocumentType.TEXT_HEAVY,
    confidence: float = 0.95,
    total_pages: int = 10,
) -> AnalysisResult:
    return AnalysisResult(
        document_type=doc_type,
        confidence=confidence,
        total_pages=total_pages,
        sampled_pages=3,
        page_features=[
            PageFeatures(
                page_number=i,
                text_char_count=500,
                image_count=0,
                image_area_ratio=0.0,
                table_count=0,
                has_extractable_text=True,
            )
            for i in range(1, 4)
        ],
        summary_metrics=SummaryMetrics(
            avg_text_chars=500.0,
            avg_image_count=0.0,
            avg_image_area_ratio=0.0,
            avg_table_count=0.0,
            extractable_text_ratio=1.0,
        ),
    )


class TestAnalyzeNode:

    @pytest.mark.asyncio
    async def test_happy_path(self):
        state = create_advanced_initial_state(
            file_bytes=b"pdf-data", filename="test.pdf",
            user_id="u1", request_id="r1",
        )
        analyzer = MagicMock()
        analyzer.analyze_bytes.return_value = _make_analysis_result()

        result = await analyze_node(state, analyzer)

        assert result["document_type"] == "text_heavy"
        assert result["analysis_confidence"] == 0.95
        assert result["total_pages"] == 10
        assert result["status"] == "analyzing"
        assert "avg_text_chars" in result["analysis_metrics"]

    @pytest.mark.asyncio
    async def test_table_heavy_type(self):
        state = create_advanced_initial_state(
            file_bytes=b"pdf", filename="t.pdf", user_id="u", request_id="r",
        )
        analyzer = MagicMock()
        analyzer.analyze_bytes.return_value = _make_analysis_result(
            doc_type=PDFDocumentType.TABLE_HEAVY,
            confidence=0.88,
        )

        result = await analyze_node(state, analyzer)

        assert result["document_type"] == "table_heavy"
        assert result["analysis_confidence"] == 0.88

    @pytest.mark.asyncio
    async def test_analyzer_exception_returns_failed(self):
        state = create_advanced_initial_state(
            file_bytes=b"pdf", filename="t.pdf", user_id="u", request_id="r",
        )
        analyzer = MagicMock()
        analyzer.analyze_bytes.side_effect = RuntimeError("PDF corrupted")

        result = await analyze_node(state, analyzer)

        assert result["status"] == "analyzing"
        assert any("Analyze failed" in e for e in result["errors"])

    @pytest.mark.asyncio
    async def test_errors_appended_to_existing(self):
        state = create_advanced_initial_state(
            file_bytes=b"pdf", filename="t.pdf", user_id="u", request_id="r",
        )
        state["errors"] = ["previous error"]
        analyzer = MagicMock()
        analyzer.analyze_bytes.side_effect = ValueError("bad")

        result = await analyze_node(state, analyzer)

        assert len(result["errors"]) == 2
        assert result["errors"][0] == "previous error"
