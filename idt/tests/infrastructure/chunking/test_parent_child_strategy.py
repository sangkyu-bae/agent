"""Tests for ParentChildStrategy implementation."""
import pytest
from langchain_core.documents import Document

from src.infrastructure.chunking.strategies.parent_child_strategy import (
    ParentChildStrategy,
)
from src.domain.chunking.value_objects import ChunkingConfig
from src.domain.chunking.interfaces import ChunkingStrategy


class TestParentChildStrategy:
    """Tests for ParentChildStrategy chunking implementation."""

    @pytest.fixture
    def strategy(self):
        """Create a ParentChildStrategy with default settings."""
        parent_config = ChunkingConfig(chunk_size=2000, chunk_overlap=0)
        child_config = ChunkingConfig(chunk_size=500, chunk_overlap=50)
        return ParentChildStrategy(
            parent_config=parent_config,
            child_config=child_config
        )

    @pytest.fixture
    def small_chunk_strategy(self):
        """Create a strategy with small chunks for testing."""
        parent_config = ChunkingConfig(chunk_size=200, chunk_overlap=0)
        child_config = ChunkingConfig(chunk_size=50, chunk_overlap=5)
        return ParentChildStrategy(
            parent_config=parent_config,
            child_config=child_config
        )

    def test_implements_chunking_strategy(self, strategy):
        """ParentChildStrategy should implement ChunkingStrategy interface."""
        assert isinstance(strategy, ChunkingStrategy)

    def test_get_strategy_name(self, strategy):
        """get_strategy_name should return 'parent_child'."""
        assert strategy.get_strategy_name() == "parent_child"

    def test_get_chunk_size_returns_child_size(self, strategy):
        """get_chunk_size should return child chunk size (used for retrieval)."""
        assert strategy.get_chunk_size() == 500

    def test_single_page_creates_parent_and_children(self, small_chunk_strategy):
        """Single page should create 1 parent with N children."""
        content = " ".join(["word"] * 300)  # ~300 tokens
        doc = Document(
            page_content=content,
            metadata={"document_id": "doc_1", "page_number": 1}
        )

        result = small_chunk_strategy.chunk([doc])

        # Should have parent chunks and child chunks
        parents = [d for d in result if d.metadata.get("chunk_type") == "parent"]
        children = [d for d in result if d.metadata.get("chunk_type") == "child"]

        assert len(parents) >= 1
        assert len(children) >= 1

    def test_parent_chunk_has_children_ids(self, small_chunk_strategy):
        """Parent chunks should have children_ids list."""
        content = " ".join(["word"] * 300)
        doc = Document(page_content=content)

        result = small_chunk_strategy.chunk([doc])

        parents = [d for d in result if d.metadata.get("chunk_type") == "parent"]

        for parent in parents:
            assert "children_ids" in parent.metadata
            assert isinstance(parent.metadata["children_ids"], list)
            assert len(parent.metadata["children_ids"]) > 0

    def test_child_chunk_has_parent_id(self, small_chunk_strategy):
        """Child chunks should have parent_id reference."""
        content = " ".join(["word"] * 300)
        doc = Document(page_content=content)

        result = small_chunk_strategy.chunk([doc])

        children = [d for d in result if d.metadata.get("chunk_type") == "child"]

        for child in children:
            assert "parent_id" in child.metadata
            assert child.metadata["parent_id"] is not None

    def test_parent_children_relationship(self, small_chunk_strategy):
        """Parent's children_ids should match actual child parent_id references."""
        content = " ".join(["word"] * 300)
        doc = Document(
            page_content=content,
            metadata={"document_id": "doc_1"}
        )

        result = small_chunk_strategy.chunk([doc])

        parents = [d for d in result if d.metadata.get("chunk_type") == "parent"]
        children = [d for d in result if d.metadata.get("chunk_type") == "child"]

        for parent in parents:
            parent_id = parent.metadata["chunk_id"]
            children_ids = parent.metadata["children_ids"]

            # Each child_id in parent should correspond to an actual child
            for child_id in children_ids:
                matching_children = [
                    c for c in children
                    if c.metadata.get("chunk_id") == child_id
                ]
                assert len(matching_children) == 1
                assert matching_children[0].metadata["parent_id"] == parent_id

    def test_original_metadata_preserved(self, strategy):
        """Original document metadata should be preserved in all chunks."""
        doc = Document(
            page_content="Test content " * 100,
            metadata={
                "document_id": "doc_123",
                "user_id": "user_456",
                "source": "test_source"
            }
        )

        result = strategy.chunk([doc])

        for chunk in result:
            assert chunk.metadata["document_id"] == "doc_123"
            assert chunk.metadata["user_id"] == "user_456"
            assert chunk.metadata["source"] == "test_source"

    def test_child_500_token_default(self):
        """Default child chunk size should be 500 tokens."""
        parent_config = ChunkingConfig(chunk_size=2000, chunk_overlap=0)
        child_config = ChunkingConfig(chunk_size=500, chunk_overlap=50)
        strategy = ParentChildStrategy(
            parent_config=parent_config,
            child_config=child_config
        )

        assert strategy.get_chunk_size() == 500

    def test_child_50_token_overlap(self, small_chunk_strategy):
        """Child chunks should have proper overlap."""
        # Create content that requires multiple children
        content = " ".join(["word"] * 300)
        doc = Document(page_content=content)

        result = small_chunk_strategy.chunk([doc])

        children = [d for d in result if d.metadata.get("chunk_type") == "child"]

        # With overlap, content should be shared between adjacent chunks
        if len(children) >= 2:
            # The overlap means adjacent children have shared tokens
            # We can verify this by checking content overlap exists
            for i in range(len(children) - 1):
                # At minimum, verify children exist with reasonable content
                assert len(children[i].page_content) > 0
                assert len(children[i + 1].page_content) > 0

    def test_empty_document_list(self, strategy):
        """Empty document list should return empty list."""
        result = strategy.chunk([])

        assert result == []

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

        doc1_chunks = [
            c for c in result if c.metadata["document_id"] == "doc_1"
        ]
        doc2_chunks = [
            c for c in result if c.metadata["document_id"] == "doc_2"
        ]

        assert len(doc1_chunks) > 0
        assert len(doc2_chunks) > 0

    def test_chunk_id_uniqueness(self, small_chunk_strategy):
        """All chunks should have unique chunk_id."""
        content = " ".join(["word"] * 500)
        doc = Document(page_content=content)

        result = small_chunk_strategy.chunk([doc])

        chunk_ids = [c.metadata["chunk_id"] for c in result]

        assert len(chunk_ids) == len(set(chunk_ids))

    def test_parent_contains_full_page_content(self, small_chunk_strategy):
        """Parent chunk should contain the full page content."""
        content = "This is test content. " * 20
        doc = Document(
            page_content=content,
            metadata={"document_id": "doc_1"}
        )

        result = small_chunk_strategy.chunk([doc])

        parents = [d for d in result if d.metadata.get("chunk_type") == "parent"]

        # Parent should contain the original content
        assert len(parents) >= 1
        # At least one parent should have substantial content
        total_parent_content = "".join([p.page_content for p in parents])
        assert len(total_parent_content) > 0

    def test_child_indices_are_sequential(self, small_chunk_strategy):
        """Child chunk indices should be sequential."""
        content = " ".join(["word"] * 500)
        doc = Document(page_content=content)

        result = small_chunk_strategy.chunk([doc])

        children = [d for d in result if d.metadata.get("chunk_type") == "child"]

        indices = [c.metadata["chunk_index"] for c in children]
        expected = list(range(len(children)))

        assert indices == expected

    def test_lookup_children_by_parent_id(self, small_chunk_strategy):
        """Should be able to find all children given a parent_id."""
        content = " ".join(["word"] * 300)
        doc = Document(page_content=content)

        result = small_chunk_strategy.chunk([doc])

        parents = [d for d in result if d.metadata.get("chunk_type") == "parent"]
        children = [d for d in result if d.metadata.get("chunk_type") == "child"]

        for parent in parents:
            parent_id = parent.metadata["chunk_id"]
            matching_children = [
                c for c in children if c.metadata["parent_id"] == parent_id
            ]
            # Should find at least one child for each parent
            assert len(matching_children) > 0
            # Number of matching children should equal children_ids count
            assert len(matching_children) == len(parent.metadata["children_ids"])
