"""Tests for parse node."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.documents import Document

from src.infrastructure.pipeline.nodes.parse_node import parse_node
from src.domain.pipeline.state.pipeline_state import PipelineState
from src.domain.parser.interfaces import PDFParserInterface


def create_initial_state(
    file_path: str = "/path/to/doc.pdf",
    file_bytes: bytes = None,
    filename: str = "doc.pdf",
    user_id: str = "user123",
) -> PipelineState:
    """Create initial pipeline state for testing."""
    return {
        "file_path": file_path,
        "file_bytes": file_bytes,
        "filename": filename,
        "user_id": user_id,
        "parsed_documents": [],
        "total_pages": 0,
        "document_id": "",
        "category": None,
        "category_confidence": 0.0,
        "classification_reasoning": "",
        "sample_pages": [],
        "chunked_documents": [],
        "chunk_count": 0,
        "chunking_config_used": {},
        "stored_ids": [],
        "collection_name": "",
        "processing_time_ms": 0,
        "errors": [],
        "status": "pending",
    }


class TestParseNodeSuccess:
    """Test parse node successful scenarios."""

    @pytest.mark.asyncio
    async def test_parse_file_path_returns_documents(self):
        """Test parsing from file_path returns documents."""
        mock_parser = MagicMock(spec=PDFParserInterface)
        mock_docs = [
            Document(page_content="Page 1 content", metadata={"page": 1, "document_id": "abc123_doc"}),
            Document(page_content="Page 2 content", metadata={"page": 2, "document_id": "abc123_doc"}),
        ]
        mock_parser.parse.return_value = mock_docs

        state = create_initial_state()
        result = await parse_node(state, mock_parser)

        assert len(result["parsed_documents"]) == 2
        assert result["total_pages"] == 2
        assert result["status"] == "parsing"
        mock_parser.parse.assert_called_once()

    @pytest.mark.asyncio
    async def test_parse_file_bytes_returns_documents(self):
        """Test parsing from file_bytes returns documents."""
        mock_parser = MagicMock(spec=PDFParserInterface)
        mock_docs = [
            Document(page_content="Byte content", metadata={"page": 1, "document_id": "xyz789_doc"}),
        ]
        mock_parser.parse_bytes.return_value = mock_docs

        state = create_initial_state(
            file_path="",
            file_bytes=b"%PDF-1.4 content",
            filename="bytes_doc.pdf",
        )
        result = await parse_node(state, mock_parser)

        assert len(result["parsed_documents"]) == 1
        assert result["total_pages"] == 1
        mock_parser.parse_bytes.assert_called_once()

    @pytest.mark.asyncio
    async def test_document_id_extracted_from_metadata(self):
        """Test document_id is extracted from document metadata."""
        mock_parser = MagicMock(spec=PDFParserInterface)
        mock_docs = [
            Document(page_content="Content", metadata={"page": 1, "document_id": "unique123_myfile"}),
        ]
        mock_parser.parse.return_value = mock_docs

        state = create_initial_state()
        result = await parse_node(state, mock_parser)

        assert result["document_id"] == "unique123_myfile"


class TestParseNodeErrorHandling:
    """Test parse node error handling."""

    @pytest.mark.asyncio
    async def test_parse_error_sets_failed_status(self):
        """Test parse error sets status to failed."""
        mock_parser = MagicMock(spec=PDFParserInterface)
        mock_parser.parse.side_effect = Exception("Parse failed: Invalid PDF")

        state = create_initial_state()
        result = await parse_node(state, mock_parser)

        assert result["status"] == "failed"
        assert len(result["errors"]) > 0
        assert "Parse failed" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_empty_documents_returns_error(self):
        """Test empty documents list returns error."""
        mock_parser = MagicMock(spec=PDFParserInterface)
        mock_parser.parse.return_value = []

        state = create_initial_state()
        result = await parse_node(state, mock_parser)

        assert result["status"] == "failed"
        assert len(result["errors"]) > 0


class TestParseNodePreferFileBytes:
    """Test parse node prefers file_bytes over file_path."""

    @pytest.mark.asyncio
    async def test_prefers_file_bytes_when_both_provided(self):
        """Test file_bytes is used when both file_bytes and file_path provided."""
        mock_parser = MagicMock(spec=PDFParserInterface)
        mock_docs = [Document(page_content="From bytes", metadata={"page": 1, "document_id": "id1"})]
        mock_parser.parse_bytes.return_value = mock_docs

        state = create_initial_state(
            file_path="/path/to/file.pdf",
            file_bytes=b"%PDF bytes",
            filename="both.pdf",
        )
        result = await parse_node(state, mock_parser)

        # Should use parse_bytes, not parse
        mock_parser.parse_bytes.assert_called_once()
        mock_parser.parse.assert_not_called()
        assert len(result["parsed_documents"]) == 1
