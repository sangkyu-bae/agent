"""Tests for FullTokenStrategy implementation."""
import pytest
from langchain_core.documents import Document

from src.infrastructure.chunking.strategies.full_token_strategy import (
    FullTokenStrategy,
)
from src.domain.chunking.value_objects import ChunkingConfig
from src.domain.chunking.interfaces import ChunkingStrategy


class TestFullTokenStrategy:
    """Tests for FullTokenStrategy chunking implementation."""

    @pytest.fixture
    def strategy(self):
        """Create a FullTokenStrategy with 2000 token chunks."""
        config = ChunkingConfig(chunk_size=2000, chunk_overlap=200)
        return FullTokenStrategy(config)

    @pytest.fixture
    def small_chunk_strategy(self):
        """Create a FullTokenStrategy with small chunks for testing."""
        config = ChunkingConfig(chunk_size=100, chunk_overlap=10)
        return FullTokenStrategy(config)

    def test_implements_chunking_strategy(self, strategy):
        """FullTokenStrategy should implement ChunkingStrategy interface."""
        assert isinstance(strategy, ChunkingStrategy)

    def test_get_strategy_name(self, strategy):
        """get_strategy_name should return 'full_token'."""
        assert strategy.get_strategy_name() == "full_token"

    def test_get_chunk_size(self, strategy):
        """get_chunk_size should return configured chunk size."""
        assert strategy.get_chunk_size() == 2000

    def test_short_document_single_chunk(self, strategy):
        """Document shorter than chunk_size should produce 1 chunk."""
        doc = Document(
            page_content="Hello world, this is a short document.",
            metadata={"document_id": "doc_1", "user_id": "user_1"}
        )

        result = strategy.chunk([doc])

        assert len(result) == 1
        assert result[0].page_content == doc.page_content
        assert result[0].metadata["document_id"] == "doc_1"
        assert result[0].metadata["user_id"] == "user_1"
        assert result[0].metadata["chunk_type"] == "full"
        assert result[0].metadata["chunk_index"] == 0
        assert result[0].metadata["total_chunks"] == 1

    def test_long_document_multiple_chunks(self, small_chunk_strategy):
        """Long document should produce multiple chunks with overlap."""
        # Create content that will span multiple 100-token chunks
        words = ["testing"] * 500  # ~500 tokens
        content = " ".join(words)
        doc = Document(
            page_content=content,
            metadata={"document_id": "doc_2", "user_id": "user_2"}
        )

        result = small_chunk_strategy.chunk([doc])

        # Should have multiple chunks
        assert len(result) > 1

        # All chunks should have correct metadata
        for i, chunk in enumerate(result):
            assert chunk.metadata["chunk_type"] == "full"
            assert chunk.metadata["chunk_index"] == i
            assert chunk.metadata["total_chunks"] == len(result)
            assert chunk.metadata["document_id"] == "doc_2"
            assert chunk.metadata["user_id"] == "user_2"

    def test_preserves_original_metadata(self, strategy):
        """Original document metadata should be preserved."""
        doc = Document(
            page_content="Test content",
            metadata={
                "document_id": "doc_123",
                "user_id": "user_456",
                "source": "test_source",
                "page_number": 5,
                "custom_field": "custom_value"
            }
        )

        result = strategy.chunk([doc])

        assert result[0].metadata["document_id"] == "doc_123"
        assert result[0].metadata["user_id"] == "user_456"
        assert result[0].metadata["source"] == "test_source"
        assert result[0].metadata["page_number"] == 5
        assert result[0].metadata["custom_field"] == "custom_value"

    def test_chunk_type_is_full(self, strategy):
        """All chunks should have chunk_type='full'."""
        doc = Document(page_content="Test content")

        result = strategy.chunk([doc])

        for chunk in result:
            assert chunk.metadata["chunk_type"] == "full"

    def test_multiple_documents(self, small_chunk_strategy):
        """Should handle multiple documents correctly."""
        docs = [
            Document(
                page_content=" ".join(["doc1"] * 200),
                metadata={"document_id": "doc_1"}
            ),
            Document(
                page_content=" ".join(["doc2"] * 200),
                metadata={"document_id": "doc_2"}
            )
        ]

        result = small_chunk_strategy.chunk(docs)

        # Should have chunks from both documents
        doc1_chunks = [c for c in result if c.metadata["document_id"] == "doc_1"]
        doc2_chunks = [c for c in result if c.metadata["document_id"] == "doc_2"]

        assert len(doc1_chunks) > 0
        assert len(doc2_chunks) > 0

        # Each document's chunks should be numbered independently
        for i, chunk in enumerate(doc1_chunks):
            assert chunk.metadata["chunk_index"] == i
            assert chunk.metadata["total_chunks"] == len(doc1_chunks)

        for i, chunk in enumerate(doc2_chunks):
            assert chunk.metadata["chunk_index"] == i
            assert chunk.metadata["total_chunks"] == len(doc2_chunks)

    def test_empty_document_list(self, strategy):
        """Empty document list should return empty list."""
        result = strategy.chunk([])

        assert result == []

    def test_empty_content_document(self, strategy):
        """Document with empty content should be handled."""
        doc = Document(page_content="", metadata={"document_id": "empty"})

        result = strategy.chunk([doc])

        # Empty content should either be skipped or return empty chunk
        # Based on implementation choice
        assert len(result) <= 1

    def test_chunk_index_accuracy(self, small_chunk_strategy):
        """Chunk indices should be accurate and sequential."""
        content = " ".join(["word"] * 1000)
        doc = Document(page_content=content)

        result = small_chunk_strategy.chunk([doc])

        indices = [c.metadata["chunk_index"] for c in result]
        expected_indices = list(range(len(result)))

        assert indices == expected_indices

    def test_total_chunks_accuracy(self, small_chunk_strategy):
        """total_chunks should be accurate for all chunks."""
        content = " ".join(["word"] * 1000)
        doc = Document(page_content=content)

        result = small_chunk_strategy.chunk([doc])

        total = len(result)
        for chunk in result:
            assert chunk.metadata["total_chunks"] == total

    def test_2000_token_default_chunking(self):
        """Default 2000 token chunks should work correctly."""
        config = ChunkingConfig(chunk_size=2000, chunk_overlap=200)
        strategy = FullTokenStrategy(config)

        # Create ~10000 tokens of content
        content = " ".join(["token"] * 10000)
        doc = Document(page_content=content)

        result = strategy.chunk([doc])

        # Should produce approximately 5-6 chunks
        # (10000 tokens / (2000 - 200 overlap) ≈ 5.5)
        assert len(result) >= 5
        assert len(result) <= 7

    def test_original_content_id_preserved(self, strategy):
        """Original document_id should be preserved in all chunks."""
        doc = Document(
            page_content="Test " * 100,
            metadata={"document_id": "original_doc_id"}
        )

        result = strategy.chunk([doc])

        for chunk in result:
            assert chunk.metadata["document_id"] == "original_doc_id"
