"""Tests for chunk node."""
import pytest
from unittest.mock import MagicMock
from langchain_core.documents import Document

from src.infrastructure.pipeline.nodes.chunk_node import chunk_node
from src.domain.pipeline.state.pipeline_state import PipelineState
from src.domain.pipeline.enums.document_category import DocumentCategory
from src.domain.chunking.interfaces import ChunkingStrategy
from src.domain.chunking.value_objects import ChunkingConfig


def create_state_after_classification(
    category: DocumentCategory = DocumentCategory.IT_SYSTEM,
    parsed_documents: list = None,
) -> PipelineState:
    """Create pipeline state after classification step."""
    if parsed_documents is None:
        parsed_documents = [
            Document(page_content="Long content " * 500, metadata={"page": 1}),
            Document(page_content="More content " * 500, metadata={"page": 2}),
        ]
    return {
        "file_path": "/path/to/doc.pdf",
        "file_bytes": None,
        "filename": "doc.pdf",
        "user_id": "user123",
        "parsed_documents": parsed_documents,
        "total_pages": len(parsed_documents),
        "document_id": "abc123_doc",
        "category": category,
        "category_confidence": 0.95,
        "classification_reasoning": "Test classification",
        "sample_pages": ["Sample page 1", "Sample page 2"],
        "chunked_documents": [],
        "chunk_count": 0,
        "chunking_config_used": {},
        "stored_ids": [],
        "collection_name": "",
        "processing_time_ms": 0,
        "errors": [],
        "status": "classifying",
    }


class TestChunkNodeSuccess:
    """Test chunk node successful scenarios."""

    @pytest.mark.asyncio
    async def test_chunk_documents_returns_chunks(self):
        """Test chunking returns chunked documents."""
        mock_strategy = MagicMock(spec=ChunkingStrategy)
        mock_strategy.chunk.return_value = [
            Document(page_content="Chunk 1", metadata={"chunk_index": 0}),
            Document(page_content="Chunk 2", metadata={"chunk_index": 1}),
            Document(page_content="Chunk 3", metadata={"chunk_index": 2}),
        ]
        mock_strategy.get_chunk_size.return_value = 2000

        state = create_state_after_classification(DocumentCategory.IT_SYSTEM)
        result = await chunk_node(state, mock_strategy)

        assert len(result["chunked_documents"]) == 3
        assert result["chunk_count"] == 3
        assert result["status"] == "chunking"

    @pytest.mark.asyncio
    async def test_chunking_config_recorded(self):
        """Test chunking config is recorded in state."""
        mock_strategy = MagicMock(spec=ChunkingStrategy)
        mock_strategy.chunk.return_value = [
            Document(page_content="Chunk", metadata={}),
        ]
        mock_strategy.get_chunk_size.return_value = 2000
        mock_strategy.get_strategy_name.return_value = "full_token"

        state = create_state_after_classification(DocumentCategory.IT_SYSTEM)
        result = await chunk_node(state, mock_strategy)

        assert result["chunking_config_used"]["chunk_size"] == 2000
        assert result["chunking_config_used"]["strategy"] == "full_token"

    @pytest.mark.asyncio
    async def test_category_metadata_added_to_chunks(self):
        """Test category metadata is added to chunks."""
        mock_strategy = MagicMock(spec=ChunkingStrategy)
        chunk1 = Document(page_content="Chunk 1", metadata={"existing": "value"})
        chunk2 = Document(page_content="Chunk 2", metadata={})
        mock_strategy.chunk.return_value = [chunk1, chunk2]
        mock_strategy.get_chunk_size.return_value = 400

        state = create_state_after_classification(DocumentCategory.HR)
        result = await chunk_node(state, mock_strategy)

        for chunk in result["chunked_documents"]:
            assert chunk.metadata["category"] == "hr"
            assert chunk.metadata["document_id"] == "abc123_doc"


class TestChunkNodeCategoryConfig:
    """Test chunk node uses correct config per category."""

    @pytest.mark.asyncio
    async def test_it_system_uses_2000_chunk_size(self):
        """Test IT_SYSTEM uses 2000 token chunks."""
        mock_strategy = MagicMock(spec=ChunkingStrategy)
        mock_strategy.chunk.return_value = [Document(page_content="C", metadata={})]
        mock_strategy.get_chunk_size.return_value = 2000
        mock_strategy.get_strategy_name.return_value = "full_token"

        state = create_state_after_classification(DocumentCategory.IT_SYSTEM)
        result = await chunk_node(state, mock_strategy)

        assert result["chunking_config_used"]["chunk_size"] == 2000

    @pytest.mark.asyncio
    async def test_hr_uses_400_chunk_size(self):
        """Test HR uses 400 token chunks."""
        mock_strategy = MagicMock(spec=ChunkingStrategy)
        mock_strategy.chunk.return_value = [Document(page_content="C", metadata={})]
        mock_strategy.get_chunk_size.return_value = 400
        mock_strategy.get_strategy_name.return_value = "full_token"

        state = create_state_after_classification(DocumentCategory.HR)
        result = await chunk_node(state, mock_strategy)

        assert result["chunking_config_used"]["chunk_size"] == 400


class TestChunkNodeErrorHandling:
    """Test chunk node error handling."""

    @pytest.mark.asyncio
    async def test_chunking_error_sets_failed_status(self):
        """Test chunking error sets status to failed."""
        mock_strategy = MagicMock(spec=ChunkingStrategy)
        mock_strategy.chunk.side_effect = Exception("Chunking failed")

        state = create_state_after_classification()
        result = await chunk_node(state, mock_strategy)

        assert result["status"] == "failed"
        assert len(result["errors"]) > 0
        assert "Chunking failed" in result["errors"][-1]

    @pytest.mark.asyncio
    async def test_empty_chunks_returns_error(self):
        """Test empty chunks list returns error."""
        mock_strategy = MagicMock(spec=ChunkingStrategy)
        mock_strategy.chunk.return_value = []

        state = create_state_after_classification()
        result = await chunk_node(state, mock_strategy)

        assert result["status"] == "failed"
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_no_category_sets_failed(self):
        """Test missing category sets failed status."""
        mock_strategy = MagicMock(spec=ChunkingStrategy)

        state = create_state_after_classification()
        state["category"] = None
        result = await chunk_node(state, mock_strategy)

        assert result["status"] == "failed"
        assert len(result["errors"]) > 0
