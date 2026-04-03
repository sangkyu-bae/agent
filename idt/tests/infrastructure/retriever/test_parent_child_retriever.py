"""Tests for ParentChildRetriever implementation.

Tests for Parent-Child hierarchy search support.
"""
import pytest
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock
from typing import List, Optional, Tuple

from src.infrastructure.retriever.parent_child_retriever import (
    ParentChildRetriever,
    ParentChildResult,
)
from src.infrastructure.retriever.qdrant_retriever import QdrantRetriever
from src.domain.retriever.interfaces.retriever_interface import RetrieverInterface
from src.domain.retriever.value_objects.metadata_filter import MetadataFilter
from src.domain.vector.interfaces import EmbeddingInterface
from src.domain.vector.entities import Document
from src.domain.vector.value_objects import DocumentId


class MockEmbedding(EmbeddingInterface):
    """Mock embedding for testing."""

    def __init__(self, dimension: int = 1536):
        self._dimension = dimension

    async def embed_text(self, text: str) -> List[float]:
        return [0.1] * self._dimension

    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [[0.1] * self._dimension for _ in texts]

    def get_dimension(self) -> int:
        return self._dimension


def create_document(
    id: str,
    content: str,
    metadata: dict = None,
    score: float = None,
) -> Document:
    """Helper to create Document for testing."""
    return Document(
        id=DocumentId(id),
        content=content,
        vector=[0.1] * 1536,
        metadata=metadata or {},
        score=score,
    )


@pytest.fixture
def mock_embedding():
    return MockEmbedding()


@pytest.fixture
def mock_client():
    """Create mock Qdrant client."""
    return AsyncMock()


@pytest.fixture
def mock_base_retriever():
    """Create mock base retriever."""
    retriever = AsyncMock(spec=RetrieverInterface)
    retriever.get_retriever_name.return_value = "mock-retriever"
    return retriever


@pytest.fixture
def parent_child_retriever(mock_client, mock_embedding):
    """Create ParentChildRetriever with mocks."""
    return ParentChildRetriever(
        client=mock_client,
        collection_name="test_collection",
        embedding=mock_embedding,
    )


class TestParentChildResultDataclass:
    """Tests for ParentChildResult dataclass."""

    def test_create_parent_child_result(self):
        """Should create ParentChildResult with required fields."""
        child = create_document("child-1", "Child content", {"parent_id": "parent-1"})
        parent = create_document("parent-1", "Parent content", {"chunk_type": "parent"})

        result = ParentChildResult(
            child=child,
            parent=parent,
            score=0.95,
            sibling_count=3,
        )

        assert result.child == child
        assert result.parent == parent
        assert result.score == 0.95
        assert result.sibling_count == 3

    def test_parent_child_result_is_dataclass(self):
        """ParentChildResult should be a dataclass."""
        from dataclasses import is_dataclass

        assert is_dataclass(ParentChildResult)


class TestParentChildRetrieverImplementsInterface:
    """Tests for interface compliance."""

    def test_implements_retriever_interface(self, parent_child_retriever):
        """ParentChildRetriever should implement RetrieverInterface."""
        assert isinstance(parent_child_retriever, RetrieverInterface)

    def test_get_retriever_name(self, parent_child_retriever):
        """Should return retriever name."""
        assert parent_child_retriever.get_retriever_name() == "parent-child-retriever"


class TestRetrieveWithParent:
    """Tests for retrieve_with_parent() method."""

    @pytest.mark.asyncio
    async def test_retrieves_children_first(self, parent_child_retriever, mock_client):
        """Should retrieve children based on query."""
        # Mock search for children
        from qdrant_client.models import ScoredPoint, Record

        mock_client.search.return_value = [
            ScoredPoint(
                id="child-1",
                version=1,
                score=0.95,
                payload={
                    "content": "Child content",
                    "parent_id": "parent-1",
                    "chunk_type": "child",
                },
                vector=[0.1] * 1536,
            )
        ]

        # Mock retrieve for parent retrieval
        mock_client.retrieve.return_value = [
            Record(
                id="parent-1",
                payload={
                    "content": "Parent content",
                    "chunk_type": "parent",
                },
                vector=[0.1] * 1536,
            )
        ]

        results = await parent_child_retriever.retrieve_with_parent("test query")

        assert len(results) == 1
        assert isinstance(results[0], ParentChildResult)

    @pytest.mark.asyncio
    async def test_extracts_parent_id_from_child(
        self, parent_child_retriever, mock_client
    ):
        """Should extract parent_id from child metadata."""
        from qdrant_client.models import ScoredPoint, Record

        mock_client.search.return_value = [
            ScoredPoint(
                id="child-1",
                version=1,
                score=0.9,
                payload={
                    "content": "Child content",
                    "parent_id": "parent-abc",
                    "chunk_type": "child",
                },
                vector=[0.1] * 1536,
            )
        ]
        mock_client.retrieve.return_value = [
            Record(
                id="parent-abc",
                payload={"content": "Parent", "chunk_type": "parent"},
                vector=[0.1] * 1536,
            )
        ]

        results = await parent_child_retriever.retrieve_with_parent("test query")

        # Verify retrieve was called with parent IDs
        retrieve_calls = mock_client.retrieve.call_args_list
        assert len(retrieve_calls) > 0

    @pytest.mark.asyncio
    async def test_deduplicates_parents(self, parent_child_retriever, mock_client):
        """Should deduplicate when multiple children have same parent."""
        from qdrant_client.models import ScoredPoint, Record

        mock_client.search.return_value = [
            ScoredPoint(
                id="child-1",
                version=1,
                score=0.95,
                payload={
                    "content": "Child 1",
                    "parent_id": "parent-1",
                    "chunk_type": "child",
                },
                vector=[0.1] * 1536,
            ),
            ScoredPoint(
                id="child-2",
                version=1,
                score=0.90,
                payload={
                    "content": "Child 2",
                    "parent_id": "parent-1",
                    "chunk_type": "child",
                },
                vector=[0.1] * 1536,
            ),
        ]
        mock_client.retrieve.return_value = [
            Record(
                id="parent-1",
                payload={"content": "Parent", "chunk_type": "parent"},
                vector=[0.1] * 1536,
            )
        ]

        results = await parent_child_retriever.retrieve_with_parent("test query")

        # Should return 2 results (one per child), but parent fetched once
        assert len(results) == 2
        # Both should have the same parent
        assert results[0].parent.id.value == results[1].parent.id.value

    @pytest.mark.asyncio
    async def test_returns_correct_scores(self, parent_child_retriever, mock_client):
        """Should return child similarity scores."""
        from qdrant_client.models import ScoredPoint, Record

        mock_client.search.return_value = [
            ScoredPoint(
                id="child-1",
                version=1,
                score=0.87,
                payload={
                    "content": "Child",
                    "parent_id": "parent-1",
                    "chunk_type": "child",
                },
                vector=[0.1] * 1536,
            )
        ]
        mock_client.retrieve.return_value = [
            Record(
                id="parent-1",
                payload={"content": "Parent", "chunk_type": "parent"},
                vector=[0.1] * 1536,
            )
        ]

        results = await parent_child_retriever.retrieve_with_parent("test query")

        assert results[0].score == 0.87

    @pytest.mark.asyncio
    async def test_applies_filters(self, parent_child_retriever, mock_client):
        """Should apply filters to child search."""
        from qdrant_client.models import ScoredPoint

        mock_client.search.return_value = []
        filters = MetadataFilter(user_id="user-123")

        await parent_child_retriever.retrieve_with_parent(
            "test query", filters=filters
        )

        call_kwargs = mock_client.search.call_args.kwargs
        # Should force chunk_type to child and add user filter
        assert call_kwargs["query_filter"] is not None

    @pytest.mark.asyncio
    async def test_empty_results(self, parent_child_retriever, mock_client):
        """Should handle empty results."""
        mock_client.search.return_value = []

        results = await parent_child_retriever.retrieve_with_parent("test query")

        assert results == []


class TestRetrieveChildrenByParent:
    """Tests for retrieve_children_by_parent() method."""

    @pytest.mark.asyncio
    async def test_retrieves_children_for_parent(
        self, parent_child_retriever, mock_client
    ):
        """Should retrieve all children for a given parent."""
        from qdrant_client.models import Record

        mock_client.scroll.return_value = (
            [
                Record(
                    id="child-1",
                    payload={
                        "content": "Child 1",
                        "parent_id": "parent-1",
                        "chunk_type": "child",
                    },
                    vector=[0.1] * 1536,
                ),
                Record(
                    id="child-2",
                    payload={
                        "content": "Child 2",
                        "parent_id": "parent-1",
                        "chunk_type": "child",
                    },
                    vector=[0.1] * 1536,
                ),
            ],
            None,
        )

        results = await parent_child_retriever.retrieve_children_by_parent("parent-1")

        assert len(results) == 2
        assert all(isinstance(doc, Document) for doc in results)

    @pytest.mark.asyncio
    async def test_filters_by_parent_id(self, parent_child_retriever, mock_client):
        """Should filter by parent_id."""
        mock_client.scroll.return_value = ([], None)

        await parent_child_retriever.retrieve_children_by_parent("parent-xyz")

        call_kwargs = mock_client.scroll.call_args.kwargs
        scroll_filter = call_kwargs["scroll_filter"]
        assert scroll_filter is not None
        # Should have parent_id condition

    @pytest.mark.asyncio
    async def test_respects_top_k(self, parent_child_retriever, mock_client):
        """Should respect top_k limit."""
        mock_client.scroll.return_value = ([], None)

        await parent_child_retriever.retrieve_children_by_parent("parent-1", top_k=5)

        call_kwargs = mock_client.scroll.call_args.kwargs
        assert call_kwargs["limit"] == 5

    @pytest.mark.asyncio
    async def test_empty_children(self, parent_child_retriever, mock_client):
        """Should handle parent with no children."""
        mock_client.scroll.return_value = ([], None)

        results = await parent_child_retriever.retrieve_children_by_parent("orphan-parent")

        assert results == []


class TestSiblingCount:
    """Tests for sibling count calculation."""

    @pytest.mark.asyncio
    async def test_sibling_count_reflects_children_with_same_parent(
        self, parent_child_retriever, mock_client
    ):
        """sibling_count should reflect number of children with same parent."""
        from qdrant_client.models import ScoredPoint, Record

        mock_client.search.return_value = [
            ScoredPoint(
                id="child-1",
                version=1,
                score=0.95,
                payload={
                    "content": "Child 1",
                    "parent_id": "parent-1",
                    "chunk_type": "child",
                },
                vector=[0.1] * 1536,
            ),
            ScoredPoint(
                id="child-2",
                version=1,
                score=0.90,
                payload={
                    "content": "Child 2",
                    "parent_id": "parent-1",
                    "chunk_type": "child",
                },
                vector=[0.1] * 1536,
            ),
            ScoredPoint(
                id="child-3",
                version=1,
                score=0.85,
                payload={
                    "content": "Child 3",
                    "parent_id": "parent-2",
                    "chunk_type": "child",
                },
                vector=[0.1] * 1536,
            ),
        ]
        # Mock retrieve to return parent records
        mock_client.retrieve.return_value = [
            Record(
                id="parent-1",
                payload={"content": "Parent 1", "chunk_type": "parent"},
                vector=[0.1] * 1536,
            ),
            Record(
                id="parent-2",
                payload={"content": "Parent 2", "chunk_type": "parent"},
                vector=[0.1] * 1536,
            ),
        ]

        results = await parent_child_retriever.retrieve_with_parent("test query")

        # Children 1 and 2 share parent-1, child 3 has parent-2
        parent1_results = [r for r in results if r.parent.id.value == "parent-1"]
        parent2_results = [r for r in results if r.parent.id.value == "parent-2"]

        assert all(r.sibling_count == 2 for r in parent1_results)
        assert all(r.sibling_count == 1 for r in parent2_results)


class TestBaseRetrieverMethods:
    """Tests for base retriever methods (inherited functionality)."""

    @pytest.mark.asyncio
    async def test_retrieve_delegates_to_base(self, parent_child_retriever, mock_client):
        """retrieve() should work like base retriever."""
        from qdrant_client.models import ScoredPoint

        mock_client.search.return_value = [
            ScoredPoint(
                id="doc-1",
                version=1,
                score=0.9,
                payload={"content": "Content"},
                vector=[0.1] * 1536,
            )
        ]

        results = await parent_child_retriever.retrieve("test query")

        assert len(results) == 1
        assert isinstance(results[0], Document)

    @pytest.mark.asyncio
    async def test_retrieve_with_scores_works(
        self, parent_child_retriever, mock_client
    ):
        """retrieve_with_scores() should work."""
        from qdrant_client.models import ScoredPoint

        mock_client.search.return_value = [
            ScoredPoint(
                id="doc-1",
                version=1,
                score=0.85,
                payload={"content": "Content"},
                vector=[0.1] * 1536,
            )
        ]

        results = await parent_child_retriever.retrieve_with_scores("test query")

        assert len(results) == 1
        assert results[0][1] == 0.85

    @pytest.mark.asyncio
    async def test_retrieve_by_metadata_works(
        self, parent_child_retriever, mock_client
    ):
        """retrieve_by_metadata() should work."""
        from qdrant_client.models import Record

        mock_client.scroll.return_value = (
            [
                Record(
                    id="doc-1",
                    payload={"content": "Content", "user_id": "user-1"},
                    vector=[0.1] * 1536,
                )
            ],
            None,
        )

        filters = MetadataFilter(user_id="user-1")
        results = await parent_child_retriever.retrieve_by_metadata(filters)

        assert len(results) == 1
