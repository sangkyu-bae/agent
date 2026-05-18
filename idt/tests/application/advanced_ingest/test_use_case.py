from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.advanced_ingest.use_case import AdvancedIngestUseCase
from src.domain.advanced_ingest.schemas import AdvancedIngestRequest


def _make_use_case():
    return AdvancedIngestUseCase(
        analyzer=MagicMock(),
        router=MagicMock(),
        parsers={"pymupdf": MagicMock()},
        layout_analyzer=MagicMock(),
        table_preprocessor=MagicMock(),
        morph_analyzer=MagicMock(),
        embedding=AsyncMock(),
        vectorstore=AsyncMock(),
        es_repo=AsyncMock(),
        logger=MagicMock(),
    )


def _make_request(**overrides):
    base = {
        "filename": "test.pdf",
        "user_id": "u1",
        "request_id": "r1",
        "file_bytes": b"pdf-data",
        "collection_name": "documents",
    }
    base.update(overrides)
    return AdvancedIngestRequest(**base)


class TestAdvancedIngestUseCase:

    @pytest.mark.asyncio
    @patch("src.application.advanced_ingest.use_case.create_advanced_processing_graph")
    @patch("src.application.advanced_ingest.use_case.create_advanced_initial_state")
    async def test_happy_path(self, mock_create_state, mock_create_graph):
        uc = _make_use_case()
        request = _make_request()

        mock_create_state.return_value = {"status": "pending", "errors": []}
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "document_id": "doc-123",
            "total_pages": 5,
            "document_type": "text_heavy",
            "analysis_confidence": 0.95,
            "routed_parser_type": "pymupdf",
            "layout_quality_score": 0.85,
            "layout_applied": True,
            "table_count": 0,
            "table_flattened": False,
            "chunk_count": 10,
            "qdrant_stored_count": 10,
            "es_stored_count": 10,
            "processing_time_ms": 2000,
            "step_timings": {"analyze": 100},
            "errors": [],
        }
        mock_create_graph.return_value = mock_graph

        result = await uc.ingest(request)

        assert result.document_id == "doc-123"
        assert result.filename == "test.pdf"
        assert result.user_id == "u1"
        assert result.total_pages == 5
        assert result.chunk_count == 10
        assert result.qdrant_indexed == 10
        assert result.es_indexed == 10
        assert result.collection_name == "documents"
        assert result.request_id == "r1"

    @pytest.mark.asyncio
    @patch("src.application.advanced_ingest.use_case.create_advanced_processing_graph")
    @patch("src.application.advanced_ingest.use_case.create_advanced_initial_state")
    async def test_graph_exception_raises(self, mock_create_state, mock_create_graph):
        uc = _make_use_case()
        request = _make_request()

        mock_create_state.return_value = {"status": "pending"}
        mock_graph = AsyncMock()
        mock_graph.ainvoke.side_effect = RuntimeError("graph explosion")
        mock_create_graph.return_value = mock_graph

        with pytest.raises(RuntimeError, match="graph explosion"):
            await uc.ingest(request)

    @pytest.mark.asyncio
    @patch("src.application.advanced_ingest.use_case.create_advanced_processing_graph")
    @patch("src.application.advanced_ingest.use_case.create_advanced_initial_state")
    async def test_logger_called(self, mock_create_state, mock_create_graph):
        uc = _make_use_case()
        request = _make_request()

        mock_create_state.return_value = {"status": "pending", "errors": []}
        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "document_id": "d",
            "total_pages": 1,
            "document_type": None,
            "analysis_confidence": 0.0,
            "routed_parser_type": "",
            "layout_quality_score": None,
            "layout_applied": False,
            "table_count": 0,
            "table_flattened": False,
            "chunk_count": 0,
            "qdrant_stored_count": 0,
            "es_stored_count": 0,
            "processing_time_ms": 0,
            "step_timings": {},
            "errors": [],
        }
        mock_create_graph.return_value = mock_graph

        await uc.ingest(request)

        assert uc._logger.info.call_count >= 2
