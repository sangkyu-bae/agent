from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.documents import Document

from src.domain.morph.schemas import MorphAnalysisResult, MorphToken
from src.domain.pdf_analyzer.schemas import (
    AnalysisResult,
    PDFDocumentType,
    PageFeatures,
    SummaryMetrics,
)
from src.domain.pdf_routing.schemas import RoutingDecision, RoutingReason
from src.domain.parser.parse_quality import ParseQualityScore
from src.domain.vector.value_objects import DocumentId
from src.infrastructure.pipeline.graph.advanced_processing_graph import (
    create_advanced_processing_graph,
)
from src.infrastructure.pipeline.state.advanced_pipeline_state import (
    create_advanced_initial_state,
)


def _build_mocks():
    analyzer = MagicMock()
    analyzer.analyze_bytes.return_value = AnalysisResult(
        document_type=PDFDocumentType.TEXT_HEAVY,
        confidence=0.95,
        total_pages=3,
        sampled_pages=3,
        page_features=[],
        summary_metrics=SummaryMetrics(
            avg_text_chars=500.0,
            avg_image_count=0.0,
            avg_image_area_ratio=0.0,
            avg_table_count=0.0,
            extractable_text_ratio=1.0,
        ),
    )

    router = MagicMock()
    router.route.return_value = RoutingDecision(
        parser_type="pymupdf",
        document_type="text_heavy",
        confidence=0.95,
        reason=RoutingReason.DOCUMENT_TYPE_MATCH,
        is_fallback=False,
    )

    pymupdf_parser = MagicMock()
    pymupdf_parser.parse_bytes.return_value = [
        Document(
            page_content="Page 1 content about finance.",
            metadata={"document_id": "doc-123", "page": 1},
        ),
    ]
    parsers = {"pymupdf": pymupdf_parser}

    layout_analyzer = MagicMock()
    quality = ParseQualityScore(
        page=1, score=0.85, text_char_count=100,
        avg_word_length=4.5, order_consistency=0.9, issues=(),
    )
    layout_analyzer.analyze.return_value = (
        [Document(page_content="layout content", metadata={})],
        quality,
    )

    from src.domain.chunking.table_content_generator import PreprocessResult
    table_preprocessor = MagicMock()
    table_preprocessor.process.return_value = PreprocessResult(
        parent_text="original", child_text="processed", table_count=0,
    )

    morph_analyzer = MagicMock()
    morph_analyzer.analyze.return_value = MorphAnalysisResult(
        tokens=(
            MorphToken(surface="금융", pos="NNG", start=0, length=2),
        ),
        text="금융",
    )

    embedding = AsyncMock()
    embedding.embed_documents.return_value = [[0.1, 0.2, 0.3]]

    vectorstore = AsyncMock()
    vectorstore.add_documents.return_value = [DocumentId(value="v-1")]

    es_repo = AsyncMock()
    es_repo.ensure_index_exists.return_value = None
    es_repo.bulk_index.return_value = 1

    return {
        "analyzer": analyzer,
        "router": router,
        "parsers": parsers,
        "layout_analyzer": layout_analyzer,
        "table_preprocessor": table_preprocessor,
        "morph_analyzer": morph_analyzer,
        "embedding": embedding,
        "vectorstore": vectorstore,
        "es_repo": es_repo,
    }


class TestAdvancedProcessingGraph:

    @pytest.mark.asyncio
    @patch("src.infrastructure.pipeline.nodes.layout_analyze_node.fitz")
    async def test_happy_path_full_pipeline(self, mock_fitz):
        mock_fitz.open.return_value = MagicMock()
        mocks = _build_mocks()

        graph = create_advanced_processing_graph(**mocks)

        initial_state = create_advanced_initial_state(
            file_bytes=b"pdf-data",
            filename="report.pdf",
            user_id="u1",
            request_id="r1",
        )

        final_state = await graph.ainvoke(initial_state)

        assert final_state["status"] == "completed"
        assert final_state["document_type"] == "text_heavy"
        assert final_state["routed_parser_type"] == "pymupdf"
        assert final_state["qdrant_stored_count"] == 1
        assert final_state["es_stored_count"] == 1
        assert final_state["morph_applied"] is True
        assert "analyze" in final_state["step_timings"]
        assert "dual_store" in final_state["step_timings"]

    @pytest.mark.asyncio
    async def test_parse_failure_stops_pipeline(self):
        mocks = _build_mocks()
        mocks["parsers"]["pymupdf"].parse_bytes.side_effect = RuntimeError("corrupt PDF")

        graph = create_advanced_processing_graph(**mocks)

        initial_state = create_advanced_initial_state(
            file_bytes=b"bad", filename="bad.pdf",
            user_id="u1", request_id="r1",
        )

        final_state = await graph.ainvoke(initial_state)

        assert final_state["status"] == "failed"
        assert any("Parse failed" in e for e in final_state["errors"])
        assert final_state["qdrant_stored_count"] == 0
