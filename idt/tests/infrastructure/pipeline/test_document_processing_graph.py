"""Tests for document processing graph."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from langchain_core.documents import Document

from src.infrastructure.pipeline.graph.document_processing_graph import (
    create_document_processing_graph,
    create_initial_state,
)
from src.domain.pipeline.state.pipeline_state import PipelineState
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
    parser.parse.return_value = [
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


class TestCreateInitialState:
    """Test create_initial_state function."""

    def test_creates_valid_state(self):
        """Test creating initial state with required fields."""
        state = create_initial_state(
            file_path="/path/to/doc.pdf",
            filename="doc.pdf",
            user_id="user123",
        )
        assert state["file_path"] == "/path/to/doc.pdf"
        assert state["filename"] == "doc.pdf"
        assert state["user_id"] == "user123"
        assert state["status"] == "pending"
        assert state["errors"] == []

    def test_creates_state_with_file_bytes(self):
        """Test creating initial state with file_bytes."""
        state = create_initial_state(
            file_path="",
            filename="bytes.pdf",
            user_id="user456",
            file_bytes=b"%PDF bytes",
        )
        assert state["file_bytes"] == b"%PDF bytes"
        assert state["file_path"] == ""


class TestDocumentProcessingGraph:
    """Test document processing graph."""

    @pytest.mark.asyncio
    async def test_full_workflow_success(
        self,
        mock_parser,
        mock_llm_provider,
        mock_chunking_strategy,
        mock_vectorstore,
        mock_embedding,
    ):
        """Test full workflow executes successfully."""
        graph = create_document_processing_graph(
            parser=mock_parser,
            llm_provider=mock_llm_provider,
            chunking_strategy=mock_chunking_strategy,
            vectorstore=mock_vectorstore,
            embedding=mock_embedding,
            collection_name="test_collection",
        )

        initial_state = create_initial_state(
            file_path="/path/to/doc.pdf",
            filename="doc.pdf",
            user_id="user123",
        )

        result = await graph.ainvoke(initial_state)

        # Verify final state
        assert result["status"] == "completed"
        assert result["category"] == DocumentCategory.IT_SYSTEM
        assert result["chunk_count"] == 2
        assert len(result["stored_ids"]) == 2
        assert result["collection_name"] == "test_collection"

    @pytest.mark.asyncio
    async def test_status_transitions(
        self,
        mock_parser,
        mock_llm_provider,
        mock_chunking_strategy,
        mock_vectorstore,
        mock_embedding,
    ):
        """Test status transitions through workflow."""
        graph = create_document_processing_graph(
            parser=mock_parser,
            llm_provider=mock_llm_provider,
            chunking_strategy=mock_chunking_strategy,
            vectorstore=mock_vectorstore,
            embedding=mock_embedding,
            collection_name="col",
        )

        initial_state = create_initial_state(
            file_path="/path/to/doc.pdf",
            filename="doc.pdf",
            user_id="user123",
        )

        result = await graph.ainvoke(initial_state)

        # Final status should be completed
        assert result["status"] == "completed"


class TestDocumentProcessingGraphErrors:
    """Test document processing graph error handling."""

    @pytest.mark.asyncio
    async def test_parse_error_stops_workflow(
        self,
        mock_llm_provider,
        mock_chunking_strategy,
        mock_vectorstore,
        mock_embedding,
    ):
        """Test parse error stops workflow."""
        failing_parser = MagicMock(spec=PDFParserInterface)
        failing_parser.parse.side_effect = Exception("Parse error")

        graph = create_document_processing_graph(
            parser=failing_parser,
            llm_provider=mock_llm_provider,
            chunking_strategy=mock_chunking_strategy,
            vectorstore=mock_vectorstore,
            embedding=mock_embedding,
            collection_name="col",
        )

        initial_state = create_initial_state(
            file_path="/path/to/doc.pdf",
            filename="doc.pdf",
            user_id="user123",
        )

        result = await graph.ainvoke(initial_state)

        assert result["status"] == "failed"
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_classify_error_stops_workflow(
        self,
        mock_parser,
        mock_chunking_strategy,
        mock_vectorstore,
        mock_embedding,
    ):
        """Test classify error stops workflow."""
        failing_llm = AsyncMock(spec=LLMProviderInterface)
        failing_llm.generate_structured.side_effect = Exception("LLM error")

        graph = create_document_processing_graph(
            parser=mock_parser,
            llm_provider=failing_llm,
            chunking_strategy=mock_chunking_strategy,
            vectorstore=mock_vectorstore,
            embedding=mock_embedding,
            collection_name="col",
        )

        initial_state = create_initial_state(
            file_path="/path/to/doc.pdf",
            filename="doc.pdf",
            user_id="user123",
        )

        result = await graph.ainvoke(initial_state)

        assert result["status"] == "failed"

    @pytest.mark.asyncio
    async def test_store_error_stops_workflow(
        self,
        mock_parser,
        mock_llm_provider,
        mock_chunking_strategy,
        mock_embedding,
    ):
        """Test store error stops workflow."""
        failing_store = AsyncMock(spec=VectorStoreInterface)
        failing_store.add_documents.side_effect = Exception("Store error")

        graph = create_document_processing_graph(
            parser=mock_parser,
            llm_provider=mock_llm_provider,
            chunking_strategy=mock_chunking_strategy,
            vectorstore=failing_store,
            embedding=mock_embedding,
            collection_name="col",
        )

        initial_state = create_initial_state(
            file_path="/path/to/doc.pdf",
            filename="doc.pdf",
            user_id="user123",
        )

        result = await graph.ainvoke(initial_state)

        assert result["status"] == "failed"
