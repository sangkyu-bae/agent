"""Tests for store node."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.documents import Document as LCDocument

from src.infrastructure.pipeline.nodes.store_node import store_node
from src.domain.pipeline.state.pipeline_state import PipelineState
from src.domain.pipeline.enums.document_category import DocumentCategory
from src.domain.vector.interfaces import VectorStoreInterface, EmbeddingInterface
from src.domain.vector.value_objects import DocumentId


def create_state_after_chunking(
    chunked_documents: list = None,
    chunk_count: int = 3,
) -> PipelineState:
    """Create pipeline state after chunking step."""
    if chunked_documents is None:
        chunked_documents = [
            LCDocument(
                page_content=f"Chunk {i} content",
                metadata={"chunk_index": i, "category": "it_system", "document_id": "abc123_doc"}
            )
            for i in range(chunk_count)
        ]
    return {
        "file_path": "/path/to/doc.pdf",
        "file_bytes": None,
        "filename": "doc.pdf",
        "user_id": "user123",
        "parsed_documents": [],
        "total_pages": 2,
        "document_id": "abc123_doc",
        "category": DocumentCategory.IT_SYSTEM,
        "category_confidence": 0.95,
        "classification_reasoning": "Test classification",
        "sample_pages": [],
        "chunked_documents": chunked_documents,
        "chunk_count": len(chunked_documents),
        "chunking_config_used": {"chunk_size": 2000, "strategy": "full_token"},
        "stored_ids": [],
        "collection_name": "",
        "processing_time_ms": 0,
        "errors": [],
        "status": "chunking",
    }


class TestStoreNodeSuccess:
    """Test store node successful scenarios."""

    @pytest.mark.asyncio
    async def test_store_documents_returns_ids(self):
        """Test storing documents returns stored IDs."""
        mock_vectorstore = AsyncMock(spec=VectorStoreInterface)
        mock_embedding = AsyncMock(spec=EmbeddingInterface)

        # Mock embedding generation
        mock_embedding.embed_documents.return_value = [
            [0.1] * 1536,
            [0.2] * 1536,
            [0.3] * 1536,
        ]

        # Mock vector store add
        mock_vectorstore.add_documents.return_value = [
            DocumentId("id1"),
            DocumentId("id2"),
            DocumentId("id3"),
        ]

        state = create_state_after_chunking()
        result = await store_node(state, mock_vectorstore, mock_embedding, "test_collection")

        assert len(result["stored_ids"]) == 3
        assert result["collection_name"] == "test_collection"
        assert result["status"] == "storing"

    @pytest.mark.asyncio
    async def test_embedding_called_for_chunks(self):
        """Test embedding is called for all chunks."""
        mock_vectorstore = AsyncMock(spec=VectorStoreInterface)
        mock_embedding = AsyncMock(spec=EmbeddingInterface)
        mock_embedding.embed_documents.return_value = [[0.1] * 1536] * 3
        mock_vectorstore.add_documents.return_value = [DocumentId("id1")] * 3

        state = create_state_after_chunking(chunk_count=3)
        await store_node(state, mock_vectorstore, mock_embedding, "test_col")

        mock_embedding.embed_documents.assert_called_once()
        call_args = mock_embedding.embed_documents.call_args[0][0]
        assert len(call_args) == 3

    @pytest.mark.asyncio
    async def test_stored_ids_are_strings(self):
        """Test stored IDs are converted to strings."""
        mock_vectorstore = AsyncMock(spec=VectorStoreInterface)
        mock_embedding = AsyncMock(spec=EmbeddingInterface)
        mock_embedding.embed_documents.return_value = [[0.1] * 1536]
        mock_vectorstore.add_documents.return_value = [DocumentId("unique_id_123")]

        state = create_state_after_chunking(chunk_count=1)
        result = await store_node(state, mock_vectorstore, mock_embedding, "col")

        assert result["stored_ids"] == ["unique_id_123"]


class TestStoreNodeErrorHandling:
    """Test store node error handling."""

    @pytest.mark.asyncio
    async def test_embedding_error_sets_failed_status(self):
        """Test embedding error sets status to failed."""
        mock_vectorstore = AsyncMock(spec=VectorStoreInterface)
        mock_embedding = AsyncMock(spec=EmbeddingInterface)
        mock_embedding.embed_documents.side_effect = Exception("Embedding API error")

        state = create_state_after_chunking()
        result = await store_node(state, mock_vectorstore, mock_embedding, "col")

        assert result["status"] == "failed"
        assert len(result["errors"]) > 0
        assert "Store failed" in result["errors"][-1]

    @pytest.mark.asyncio
    async def test_vectorstore_error_sets_failed_status(self):
        """Test vectorstore error sets status to failed."""
        mock_vectorstore = AsyncMock(spec=VectorStoreInterface)
        mock_embedding = AsyncMock(spec=EmbeddingInterface)
        mock_embedding.embed_documents.return_value = [[0.1] * 1536]
        mock_vectorstore.add_documents.side_effect = Exception("Qdrant connection error")

        state = create_state_after_chunking(chunk_count=1)
        result = await store_node(state, mock_vectorstore, mock_embedding, "col")

        assert result["status"] == "failed"
        assert "Store failed" in result["errors"][-1]

    @pytest.mark.asyncio
    async def test_empty_chunks_sets_failed(self):
        """Test empty chunks list sets failed status."""
        mock_vectorstore = AsyncMock(spec=VectorStoreInterface)
        mock_embedding = AsyncMock(spec=EmbeddingInterface)

        state = create_state_after_chunking(chunked_documents=[])
        result = await store_node(state, mock_vectorstore, mock_embedding, "col")

        assert result["status"] == "failed"
        assert len(result["errors"]) > 0


class TestStoreNodeMetadata:
    """Test store node metadata handling."""

    @pytest.mark.asyncio
    async def test_user_id_added_to_metadata(self):
        """Test user_id is added to document metadata."""
        mock_vectorstore = AsyncMock(spec=VectorStoreInterface)
        mock_embedding = AsyncMock(spec=EmbeddingInterface)
        mock_embedding.embed_documents.return_value = [[0.1] * 1536]
        mock_vectorstore.add_documents.return_value = [DocumentId("id1")]

        state = create_state_after_chunking(chunk_count=1)
        await store_node(state, mock_vectorstore, mock_embedding, "col")

        # Check that add_documents was called
        call_args = mock_vectorstore.add_documents.call_args[0][0]
        assert len(call_args) == 1
        # The metadata should include user_id
        assert call_args[0].metadata.get("user_id") == "user123"
