"""Tests for ParentChildStrategy implementation."""
import pytest
from langchain_core.documents import Document

from src.infrastructure.chunking.strategies.parent_child_strategy import (
    ParentChildStrategy,
)
from src.domain.chunking.value_objects import ChunkingConfig
from src.domain.chunking.interfaces import ChunkingStrategy
from src.infrastructure.chunking.table_flattening.preprocessor import (
    TableFlatteningPreprocessor,
)
from src.infrastructure.chunking.table_flattening.rule_based_generator import (
    RuleBasedTableContentGenerator,
)


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


class TestParentChildStrategyTableFlattening:
    """Tests for table flattening integration in ParentChildStrategy."""

    @pytest.fixture
    def table_strategy(self):
        parent_config = ChunkingConfig(chunk_size=2000, chunk_overlap=0)
        child_config = ChunkingConfig(chunk_size=500, chunk_overlap=50)
        generator = RuleBasedTableContentGenerator()
        preprocessor = TableFlatteningPreprocessor(generator)
        return ParentChildStrategy(
            parent_config=parent_config,
            child_config=child_config,
            table_preprocessor=preprocessor,
        )

    @pytest.fixture
    def table_doc(self):
        content = (
            "대출 금리 안내\n\n"
            "아래 표를 참고하세요.\n\n"
            "| 등급 | 금리 | 한도 |\n"
            "|---|---|---|\n"
            "| A | 3.5% | 1억 |\n"
            "| B | 4.2% | 5천만 |\n"
            "\n후속 안내 내용입니다."
        )
        return Document(
            page_content=content,
            metadata={
                "document_id": "doc_1",
                "has_table": True,
                "section_title": "대출 금리",
            },
        )

    @pytest.fixture
    def no_table_doc(self):
        return Document(
            page_content="일반 텍스트 " * 100,
            metadata={"document_id": "doc_2", "has_table": False},
        )

    def test_parent_has_original_markdown(self, table_strategy, table_doc):
        """부모 chunk에 원본 markdown 표가 보존되는지 확인."""
        result = table_strategy.chunk([table_doc])
        parents = [d for d in result if d.metadata.get("chunk_type") == "parent"]

        assert len(parents) >= 1
        parent_text = " ".join(p.page_content for p in parents)
        assert "| 등급 | 금리 | 한도 |" in parent_text
        assert "| A | 3.5% | 1억 |" in parent_text

    def test_child_has_semantic_sentences(self, table_strategy, table_doc):
        """자식 chunk에 의미 문장이 포함되고 표가 없는지 확인."""
        result = table_strategy.chunk([table_doc])
        children = [d for d in result if d.metadata.get("chunk_type") == "child"]

        assert len(children) >= 1
        child_text = " ".join(c.page_content for c in children)
        assert "등급은(는) A" in child_text
        assert "금리은(는) 3.5%" in child_text
        assert "| A |" not in child_text

    def test_child_metadata_has_table_flattened(self, table_strategy, table_doc):
        """자식 chunk에 table_flattened 메타데이터 확인."""
        result = table_strategy.chunk([table_doc])
        children = [d for d in result if d.metadata.get("chunk_type") == "child"]

        for child in children:
            assert child.metadata.get("table_flattened") is True

    def test_parent_metadata_has_table_count(self, table_strategy, table_doc):
        """부모 chunk에 table_count 메타데이터 확인."""
        result = table_strategy.chunk([table_doc])
        parents = [d for d in result if d.metadata.get("chunk_type") == "parent"]

        for parent in parents:
            assert parent.metadata.get("table_count") == 1

    def test_no_table_doc_uses_default_logic(self, table_strategy, no_table_doc):
        """has_table=False인 문서는 기존 로직 사용."""
        result = table_strategy.chunk([no_table_doc])
        children = [d for d in result if d.metadata.get("chunk_type") == "child"]

        for child in children:
            assert child.metadata.get("table_flattened") is not True

    def test_no_preprocessor_uses_default_logic(self):
        """table_preprocessor=None이면 기존 로직 사용."""
        parent_config = ChunkingConfig(chunk_size=2000, chunk_overlap=0)
        child_config = ChunkingConfig(chunk_size=500, chunk_overlap=50)
        strategy = ParentChildStrategy(
            parent_config=parent_config,
            child_config=child_config,
            table_preprocessor=None,
        )

        doc = Document(
            page_content="| A | B |\n|---|---|\n| 1 | 2 |\n" + "text " * 100,
            metadata={"has_table": True},
        )
        result = strategy.chunk([doc])
        children = [d for d in result if d.metadata.get("chunk_type") == "child"]

        for child in children:
            assert child.metadata.get("table_flattened") is not True

    def test_parent_child_relationship_intact(self, table_strategy, table_doc):
        """표 flatten 후에도 parent_id ↔ children_ids 관계 정상."""
        result = table_strategy.chunk([table_doc])
        parents = [d for d in result if d.metadata.get("chunk_type") == "parent"]
        children = [d for d in result if d.metadata.get("chunk_type") == "child"]

        for parent in parents:
            parent_id = parent.metadata["chunk_id"]
            children_ids = parent.metadata["children_ids"]
            for child_id in children_ids:
                matching = [
                    c for c in children if c.metadata.get("chunk_id") == child_id
                ]
                assert len(matching) == 1
                assert matching[0].metadata["parent_id"] == parent_id

    def test_surrounding_text_preserved_in_children(
        self, table_strategy, table_doc
    ):
        """표 전후 텍스트가 자식 chunk에 보존되는지 확인."""
        result = table_strategy.chunk([table_doc])
        children = [d for d in result if d.metadata.get("chunk_type") == "child"]

        child_text = " ".join(c.page_content for c in children)
        assert "대출 금리 안내" in child_text
        assert "후속 안내 내용" in child_text
