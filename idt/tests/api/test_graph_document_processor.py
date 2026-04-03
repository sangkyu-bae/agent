"""Tests for GraphDocumentProcessor."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.documents import Document

from src.api.routes.document_upload import GraphDocumentProcessor
from src.domain.pipeline.enums.document_category import DocumentCategory
from src.domain.pipeline.schemas.classification_schema import ClassificationResult
from src.domain.parser.interfaces import PDFParserInterface
from src.domain.compressor.interfaces.llm_provider_interface import LLMProviderInterface
from src.domain.chunking.interfaces import ChunkingStrategy
from src.domain.vector.interfaces import VectorStoreInterface, EmbeddingInterface
from src.domain.vector.value_objects import DocumentId


@pytest.fixture
def mock_parser():
    """Create mock PDF parser."""
    parser = MagicMock(spec=PDFParserInterface)
    parser.parse_bytes.return_value = [
        Document(page_content="Page 1 content", metadata={"page": 1, "document_id": "abc123_test"}),
        Document(page_content="Page 2 content", metadata={"page": 2, "document_id": "abc123_test"}),
    ]
    return parser


@pytest.fixture
def mock_llm_provider():
    """Create mock LLM provider."""
    llm = AsyncMock(spec=LLMProviderInterface)
    llm.generate_structured.return_value = ClassificationResult(
        category=DocumentCategory.IT_SYSTEM,
        confidence=0.92,
        reasoning="Technical documentation",
    )
    return llm


@pytest.fixture
def mock_chunking_strategy():
    """Create mock chunking strategy."""
    strategy = MagicMock(spec=ChunkingStrategy)
    strategy.chunk.return_value = [
        Document(page_content="Chunk 1", metadata={"chunk_index": 0}),
        Document(page_content="Chunk 2", metadata={"chunk_index": 1}),
    ]
    strategy.get_chunk_size.return_value = 2000
    strategy.get_strategy_name.return_value = "full_token"
    return strategy


def make_processor(mock_parser, mock_llm_provider, mock_vectorstore, mock_embedding, **kwargs):
    """Helper to create GraphDocumentProcessor with new constructor signature."""
    return GraphDocumentProcessor(
        parser=mock_parser,
        llm_provider=mock_llm_provider,
        vectorstore=mock_vectorstore,
        embedding=mock_embedding,
        collection_name=kwargs.get("collection_name", "test_collection"),
        parent_chunk_size=kwargs.get("parent_chunk_size", 2000),
        default_child_chunk_size=kwargs.get("default_child_chunk_size", 500),
        child_chunk_overlap=kwargs.get("child_chunk_overlap", 50),
    )


@pytest.fixture
def mock_vectorstore():
    """Create mock vector store."""
    store = AsyncMock(spec=VectorStoreInterface)
    store.add_documents.return_value = [DocumentId("id1"), DocumentId("id2")]
    return store


@pytest.fixture
def mock_embedding():
    """Create mock embedding."""
    embed = AsyncMock(spec=EmbeddingInterface)
    embed.embed_documents.return_value = [[0.1] * 1536, [0.2] * 1536]
    return embed


class TestGraphDocumentProcessor:
    """Test GraphDocumentProcessor."""

    @pytest.mark.asyncio
    async def test_process_returns_completed_result(
        self,
        mock_parser,
        mock_llm_provider,
        mock_vectorstore,
        mock_embedding,
    ):
        """Test process returns completed result."""
        processor = make_processor(mock_parser, mock_llm_provider, mock_vectorstore, mock_embedding)

        result = await processor.process(
            file_bytes=b"%PDF-1.4 content",
            filename="test.pdf",
            user_id="user123",
        )

        assert result["status"] == "completed"
        assert result["document_id"] == "abc123_test"
        assert result["filename"] == "test.pdf"
        assert result["category"] == DocumentCategory.IT_SYSTEM
        assert result["chunk_count"] >= 1
        assert len(result["stored_ids"]) >= 1

    @pytest.mark.asyncio
    async def test_process_calls_parser_with_bytes(
        self,
        mock_parser,
        mock_llm_provider,
        mock_vectorstore,
        mock_embedding,
    ):
        """Test process calls parser with file bytes."""
        processor = make_processor(mock_parser, mock_llm_provider, mock_vectorstore, mock_embedding, collection_name="col")

        await processor.process(
            file_bytes=b"%PDF bytes",
            filename="doc.pdf",
            user_id="user456",
        )

        mock_parser.parse_bytes.assert_called_once()
        call_kwargs = mock_parser.parse_bytes.call_args
        assert call_kwargs[1]["file_bytes"] == b"%PDF bytes"
        assert call_kwargs[1]["filename"] == "doc.pdf"
        assert call_kwargs[1]["user_id"] == "user456"

    @pytest.mark.asyncio
    async def test_process_handles_parse_error(
        self,
        mock_llm_provider,
        mock_vectorstore,
        mock_embedding,
    ):
        """Test process handles parse error gracefully."""
        failing_parser = MagicMock(spec=PDFParserInterface)
        failing_parser.parse_bytes.side_effect = Exception("Invalid PDF")

        processor = make_processor(failing_parser, mock_llm_provider, mock_vectorstore, mock_embedding, collection_name="col")

        result = await processor.process(
            file_bytes=b"not a pdf",
            filename="bad.pdf",
            user_id="user123",
        )

        assert result["status"] == "failed"
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_process_includes_processing_time(
        self,
        mock_parser,
        mock_llm_provider,
        mock_vectorstore,
        mock_embedding,
    ):
        """Test process includes processing time."""
        processor = make_processor(mock_parser, mock_llm_provider, mock_vectorstore, mock_embedding, collection_name="col")

        result = await processor.process(
            file_bytes=b"%PDF",
            filename="test.pdf",
            user_id="user123",
        )

        assert "processing_time_ms" in result
        assert result["processing_time_ms"] >= 0

    @pytest.mark.asyncio
    async def test_process_with_custom_child_chunk_size(
        self,
        mock_parser,
        mock_llm_provider,
        mock_vectorstore,
        mock_embedding,
    ):
        """Test process uses custom child_chunk_size when provided."""
        processor = make_processor(
            mock_parser, mock_llm_provider, mock_vectorstore, mock_embedding,
            default_child_chunk_size=500,
        )

        result = await processor.process(
            file_bytes=b"%PDF-1.4 content",
            filename="test.pdf",
            user_id="user123",
            child_chunk_size=300,
        )

        assert result["status"] == "completed"
        # chunking_config_used should reflect child chunk size 300
        assert result.get("chunking_config_used", {}).get("child_chunk_size") == 300

    @pytest.mark.asyncio
    async def test_process_uses_default_child_chunk_size_when_not_given(
        self,
        mock_parser,
        mock_llm_provider,
        mock_vectorstore,
        mock_embedding,
    ):
        """Test process uses default_child_chunk_size when child_chunk_size is None."""
        processor = make_processor(
            mock_parser, mock_llm_provider, mock_vectorstore, mock_embedding,
            default_child_chunk_size=500,
        )

        result = await processor.process(
            file_bytes=b"%PDF-1.4 content",
            filename="test.pdf",
            user_id="user123",
        )

        assert result["status"] == "completed"
        assert result.get("chunking_config_used", {}).get("child_chunk_size") == 500
