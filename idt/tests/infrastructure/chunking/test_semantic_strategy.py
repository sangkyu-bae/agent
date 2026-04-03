"""Tests for SemanticStrategy implementation."""
import pytest
from langchain_core.documents import Document

from src.infrastructure.chunking.strategies.semantic_strategy import SemanticStrategy
from src.domain.chunking.value_objects import ChunkingConfig
from src.domain.chunking.interfaces import ChunkingStrategy


class TestSemanticStrategy:
    """Tests for SemanticStrategy chunking implementation."""

    @pytest.fixture
    def strategy(self):
        """Strategy with max 1000 tokens, min 50 tokens (for test efficiency)."""
        config = ChunkingConfig(chunk_size=1000, chunk_overlap=0)
        return SemanticStrategy(config, min_chunk_size=50)

    @pytest.fixture
    def paragraphed_doc(self):
        """Document with clear paragraph boundaries."""
        p1 = "alpha " * 60   # ~60 tokens
        p2 = "beta " * 60    # ~60 tokens
        p3 = "gamma " * 60   # ~60 tokens
        return Document(
            page_content=p1 + "\n\n" + p2 + "\n\n" + p3,
            metadata={"document_id": "doc_1", "user_id": "user_1"},
        )

    # ── 인터페이스 준수 ──────────────────────────────────────────────────────

    def test_implements_chunking_strategy(self, strategy):
        """SemanticStrategy should implement ChunkingStrategy interface."""
        assert isinstance(strategy, ChunkingStrategy)

    def test_get_strategy_name(self, strategy):
        """get_strategy_name should return 'semantic'."""
        assert strategy.get_strategy_name() == "semantic"

    def test_get_chunk_size_returns_max(self, strategy):
        """get_chunk_size should return the configured max chunk size."""
        assert strategy.get_chunk_size() == 1000

    # ── 기본 동작 ────────────────────────────────────────────────────────────

    def test_empty_document_list_returns_empty(self, strategy):
        """Empty document list should return empty list."""
        assert strategy.chunk([]) == []

    def test_empty_content_document_returns_empty(self, strategy):
        """Document with empty content should return empty list."""
        doc = Document(page_content="")
        assert strategy.chunk([doc]) == []

    def test_short_document_single_chunk(self, strategy):
        """Document shorter than max_chunk_size should produce 1 chunk."""
        doc = Document(page_content="word " * 20)
        result = strategy.chunk([doc])
        assert len(result) == 1

    # ── 문단 경계 분할 ────────────────────────────────────────────────────────

    def test_paragraph_boundary_splits_into_multiple_chunks(
        self, strategy, paragraphed_doc
    ):
        """Document with \\n\\n boundaries should be split into multiple chunks."""
        result = strategy.chunk([paragraphed_doc])
        assert len(result) >= 2

    def test_no_paragraph_boundary_fallback_to_token_split(self, strategy):
        """Document without \\n\\n should still produce output (token-based fallback)."""
        content = "word " * 200   # exceeds min, within max
        doc = Document(page_content=content)
        result = strategy.chunk([doc])
        assert len(result) >= 1

    def test_paragraph_too_long_is_split_further(self):
        """Paragraph exceeding max_chunk_size should be split by tokens."""
        config = ChunkingConfig(chunk_size=100, chunk_overlap=0)
        strategy = SemanticStrategy(config, min_chunk_size=10)
        # Single paragraph of 300 tokens → must be split
        content = "word " * 300
        doc = Document(page_content=content)
        result = strategy.chunk([doc])
        assert len(result) > 1

    def test_short_paragraphs_are_merged(self):
        """Paragraphs shorter than min_chunk_size should be merged with adjacent."""
        config = ChunkingConfig(chunk_size=1000, chunk_overlap=0)
        strategy = SemanticStrategy(config, min_chunk_size=100)
        # Two tiny paragraphs (5 tokens each) → should merge into one chunk
        p1 = "tiny "   * 5
        p2 = "small " * 5
        doc = Document(page_content=p1 + "\n\n" + p2)
        result = strategy.chunk([doc])
        # Should produce 1 merged chunk rather than 2 tiny ones
        assert len(result) == 1

    # ── 메타데이터 ────────────────────────────────────────────────────────────

    def test_chunk_type_is_semantic(self, strategy, paragraphed_doc):
        """All chunks should have chunk_type='semantic'."""
        result = strategy.chunk([paragraphed_doc])
        for chunk in result:
            assert chunk.metadata["chunk_type"] == "semantic"

    def test_semantic_boundary_recorded_in_metadata(self, strategy, paragraphed_doc):
        """Each chunk should record the semantic_boundary type."""
        result = strategy.chunk([paragraphed_doc])
        for chunk in result:
            assert "semantic_boundary" in chunk.metadata
            assert chunk.metadata["semantic_boundary"] in (
                "paragraph", "token", "full"
            )

    def test_chunk_index_in_metadata(self, strategy, paragraphed_doc):
        """Each chunk should have a sequential chunk_index."""
        result = strategy.chunk([paragraphed_doc])
        indices = [c.metadata["chunk_index"] for c in result]
        assert indices == list(range(len(result)))

    def test_total_chunks_in_metadata(self, strategy, paragraphed_doc):
        """total_chunks should be consistent across all chunks."""
        result = strategy.chunk([paragraphed_doc])
        total = len(result)
        for chunk in result:
            assert chunk.metadata["total_chunks"] == total

    def test_original_metadata_preserved(self, strategy, paragraphed_doc):
        """Original document metadata must be preserved in all chunks."""
        result = strategy.chunk([paragraphed_doc])
        for chunk in result:
            assert chunk.metadata["document_id"] == "doc_1"
            assert chunk.metadata["user_id"] == "user_1"

    # ── 복수 문서 ────────────────────────────────────────────────────────────

    def test_multiple_documents_processed_independently(self, strategy):
        """Each document's chunks should be independent."""
        docs = [
            Document(
                page_content="alpha " * 60 + "\n\n" + "beta " * 60,
                metadata={"document_id": "doc_a"},
            ),
            Document(
                page_content="gamma " * 60 + "\n\n" + "delta " * 60,
                metadata={"document_id": "doc_b"},
            ),
        ]
        result = strategy.chunk(docs)

        doc_a_chunks = [c for c in result if c.metadata["document_id"] == "doc_a"]
        doc_b_chunks = [c for c in result if c.metadata["document_id"] == "doc_b"]

        assert len(doc_a_chunks) >= 1
        assert len(doc_b_chunks) >= 1

        # Each document's chunk_index is independent
        a_indices = [c.metadata["chunk_index"] for c in doc_a_chunks]
        assert a_indices == list(range(len(doc_a_chunks)))
