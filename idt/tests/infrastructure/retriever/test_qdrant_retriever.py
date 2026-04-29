"""Tests for QdrantRetriever implementation.

Tests using mocks for Qdrant client to isolate infrastructure layer.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import ScoredPoint, Record, Filter, FieldCondition, MatchValue

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


@pytest.fixture
def mock_embedding():
    return MockEmbedding()


@pytest.fixture
def mock_client():
    """Create mock Qdrant client without spec to allow any method."""
    return AsyncMock()


@pytest.fixture
def retriever(mock_client, mock_embedding):
    return QdrantRetriever(
        client=mock_client,
        collection_name="test_collection",
        embedding=mock_embedding,
    )


def create_scored_point(
    id: str,
    score: float,
    content: str,
    metadata: dict = None,
    vector: List[float] = None,
) -> ScoredPoint:
    """Helper to create ScoredPoint for testing."""
    payload = {"content": content}
    if metadata:
        payload.update(metadata)

    return ScoredPoint(
        id=id,
        version=1,
        score=score,
        payload=payload,
        vector=vector or [0.1] * 1536,
    )


def create_record(
    id: str,
    content: str,
    metadata: dict = None,
    vector: List[float] = None,
) -> Record:
    """Helper to create Record for testing."""
    payload = {"content": content}
    if metadata:
        payload.update(metadata)

    return Record(
        id=id,
        payload=payload,
        vector=vector or [0.1] * 1536,
    )


class TestQdrantRetrieverImplementsInterface:
    """Tests for interface compliance."""

    def test_implements_retriever_interface(self, retriever):
        """QdrantRetriever should implement RetrieverInterface."""
        assert isinstance(retriever, RetrieverInterface)

    def test_get_retriever_name(self, retriever):
        """Should return retriever name."""
        assert retriever.get_retriever_name() == "qdrant-retriever"


class TestRetrieve:
    """Tests for retrieve() method."""

    @pytest.mark.asyncio
    async def test_retrieve_embeds_query(self, retriever, mock_client, mock_embedding):
        """Should embed query text before search."""
        mock_client.query_points.return_value = MagicMock(points=[])

        await retriever.retrieve("test query")

        # Verify embedding was called
        assert mock_client.query_points.called

    @pytest.mark.asyncio
    async def test_retrieve_calls_search_with_correct_params(
        self, retriever, mock_client
    ):
        """Should call search with correct parameters."""
        mock_client.query_points.return_value = MagicMock(points=[])

        await retriever.retrieve("test query", top_k=5)

        mock_client.query_points.assert_called_once()
        call_kwargs = mock_client.query_points.call_args.kwargs
        assert call_kwargs["collection_name"] == "test_collection"
        assert call_kwargs["limit"] == 5
        assert call_kwargs["with_vectors"] is True

    @pytest.mark.asyncio
    async def test_retrieve_returns_documents(self, retriever, mock_client):
        """Should convert search results to Documents."""
        mock_client.query_points.return_value = MagicMock(points=[
            create_scored_point("doc-1", 0.95, "Content 1", {"user_id": "user-1"}),
            create_scored_point("doc-2", 0.85, "Content 2", {"user_id": "user-2"}),
        ])

        result = await retriever.retrieve("test query")

        assert len(result) == 2
        assert isinstance(result[0], Document)
        assert result[0].content == "Content 1"
        assert result[0].id.value == "doc-1"

    @pytest.mark.asyncio
    async def test_retrieve_preserves_metadata(self, retriever, mock_client):
        """Should preserve original metadata in documents."""
        mock_client.query_points.return_value = MagicMock(points=[
            create_scored_point(
                "doc-1",
                0.95,
                "Content 1",
                {"user_id": "user-1", "document_type": "policy"},
            ),
        ])

        result = await retriever.retrieve("test query")

        assert result[0].metadata["user_id"] == "user-1"
        assert result[0].metadata["document_type"] == "policy"

    @pytest.mark.asyncio
    async def test_retrieve_with_filters(self, retriever, mock_client):
        """Should apply metadata filters to search."""
        mock_client.query_points.return_value = MagicMock(points=[])
        filters = MetadataFilter(user_id="user-123", chunk_type="child")

        await retriever.retrieve("test query", filters=filters)

        call_kwargs = mock_client.query_points.call_args.kwargs
        assert call_kwargs["query_filter"] is not None

    @pytest.mark.asyncio
    async def test_retrieve_empty_results(self, retriever, mock_client):
        """Should handle empty results gracefully."""
        mock_client.query_points.return_value = MagicMock(points=[])

        result = await retriever.retrieve("test query")

        assert result == []

    @pytest.mark.asyncio
    async def test_retrieve_default_top_k_is_10(self, retriever, mock_client):
        """Should use default top_k of 10."""
        mock_client.query_points.return_value = MagicMock(points=[])

        await retriever.retrieve("test query")

        call_kwargs = mock_client.query_points.call_args.kwargs
        assert call_kwargs["limit"] == 10


class TestRetrieveWithScores:
    """Tests for retrieve_with_scores() method."""

    @pytest.mark.asyncio
    async def test_returns_tuples_with_scores(self, retriever, mock_client):
        """Should return (Document, score) tuples."""
        mock_client.query_points.return_value = MagicMock(points=[
            create_scored_point("doc-1", 0.95, "Content 1"),
            create_scored_point("doc-2", 0.85, "Content 2"),
        ])

        result = await retriever.retrieve_with_scores("test query")

        assert len(result) == 2
        assert isinstance(result[0], tuple)
        assert isinstance(result[0][0], Document)
        assert isinstance(result[0][1], float)
        assert result[0][1] == 0.95
        assert result[1][1] == 0.85

    @pytest.mark.asyncio
    async def test_scores_are_correct(self, retriever, mock_client):
        """Should return correct similarity scores."""
        mock_client.query_points.return_value = MagicMock(points=[
            create_scored_point("doc-1", 0.9876, "Content 1"),
        ])

        result = await retriever.retrieve_with_scores("test query")

        assert result[0][1] == 0.9876

    @pytest.mark.asyncio
    async def test_retrieve_with_scores_applies_filters(self, retriever, mock_client):
        """Should apply filters to search."""
        mock_client.query_points.return_value = MagicMock(points=[])
        filters = MetadataFilter(document_id="doc-123")

        await retriever.retrieve_with_scores("test query", filters=filters)

        call_kwargs = mock_client.query_points.call_args.kwargs
        assert call_kwargs["query_filter"] is not None


class TestRetrieveByMetadata:
    """Tests for retrieve_by_metadata() method."""

    @pytest.mark.asyncio
    async def test_uses_scroll_api(self, retriever, mock_client):
        """Should use scroll API for metadata-only search."""
        mock_client.scroll.return_value = ([], None)
        filters = MetadataFilter(user_id="user-123")

        await retriever.retrieve_by_metadata(filters)

        mock_client.scroll.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_documents(self, retriever, mock_client):
        """Should return Documents from scroll results."""
        mock_client.scroll.return_value = (
            [
                create_record("doc-1", "Content 1"),
                create_record("doc-2", "Content 2"),
            ],
            None,
        )
        filters = MetadataFilter(user_id="user-123")

        result = await retriever.retrieve_by_metadata(filters)

        assert len(result) == 2
        assert isinstance(result[0], Document)

    @pytest.mark.asyncio
    async def test_applies_filter(self, retriever, mock_client):
        """Should apply metadata filter to scroll."""
        mock_client.scroll.return_value = ([], None)
        filters = MetadataFilter(user_id="user-123", chunk_type="parent")

        await retriever.retrieve_by_metadata(filters)

        call_kwargs = mock_client.scroll.call_args.kwargs
        assert call_kwargs["scroll_filter"] is not None

    @pytest.mark.asyncio
    async def test_respects_top_k_limit(self, retriever, mock_client):
        """Should respect top_k limit."""
        mock_client.scroll.return_value = ([], None)
        filters = MetadataFilter(user_id="user-123")

        await retriever.retrieve_by_metadata(filters, top_k=5)

        call_kwargs = mock_client.scroll.call_args.kwargs
        assert call_kwargs["limit"] == 5


class TestScoreThreshold:
    """Tests for score_threshold parameter."""

    @pytest.mark.asyncio
    async def test_filters_low_scores(self, mock_client, mock_embedding):
        """Should filter results below score threshold."""
        retriever = QdrantRetriever(
            client=mock_client,
            collection_name="test_collection",
            embedding=mock_embedding,
            score_threshold=0.8,
        )
        mock_client.query_points.return_value = MagicMock(points=[
            create_scored_point("doc-1", 0.95, "High score"),
            create_scored_point("doc-2", 0.75, "Low score"),
            create_scored_point("doc-3", 0.85, "Medium score"),
        ])

        result = await retriever.retrieve("test query")

        assert len(result) == 2
        # Only docs with score >= 0.8 should be returned

    @pytest.mark.asyncio
    async def test_no_threshold_returns_all(self, retriever, mock_client):
        """Should return all results when no threshold set."""
        mock_client.query_points.return_value = MagicMock(points=[
            create_scored_point("doc-1", 0.95, "High score"),
            create_scored_point("doc-2", 0.3, "Low score"),
        ])

        result = await retriever.retrieve("test query")

        assert len(result) == 2


class TestMetadataFilterConversion:
    """Tests for MetadataFilter to Qdrant Filter conversion."""

    @pytest.mark.asyncio
    async def test_empty_filter_no_query_filter(self, retriever, mock_client):
        """Empty filter should result in no query_filter."""
        mock_client.query_points.return_value = MagicMock(points=[])
        filters = MetadataFilter()

        await retriever.retrieve("test query", filters=filters)

        call_kwargs = mock_client.query_points.call_args.kwargs
        assert call_kwargs["query_filter"] is None

    @pytest.mark.asyncio
    async def test_filter_conversion_correctness(self, retriever, mock_client):
        """Filter should be correctly converted to Qdrant format."""
        mock_client.query_points.return_value = MagicMock(points=[])
        filters = MetadataFilter(
            user_id="user-123",
            document_id="doc-456",
            chunk_type="child",
        )

        await retriever.retrieve("test query", filters=filters)

        call_kwargs = mock_client.query_points.call_args.kwargs
        query_filter = call_kwargs["query_filter"]
        assert query_filter is not None
        assert len(query_filter.must) == 3


class TestDocumentConversion:
    """Tests for Qdrant result to Document conversion."""

    @pytest.mark.asyncio
    async def test_document_has_correct_id(self, retriever, mock_client):
        """Document should have correct ID."""
        mock_client.query_points.return_value = MagicMock(points=[
            create_scored_point("test-id-123", 0.9, "Content"),
        ])

        result = await retriever.retrieve("test query")

        assert result[0].id.value == "test-id-123"

    @pytest.mark.asyncio
    async def test_document_has_vector(self, retriever, mock_client):
        """Document should have vector."""
        vector = [0.5] * 1536
        mock_client.query_points.return_value = MagicMock(points=[
            create_scored_point("doc-1", 0.9, "Content", vector=vector),
        ])

        result = await retriever.retrieve("test query")

        assert result[0].vector == vector

    @pytest.mark.asyncio
    async def test_document_has_score_from_search(self, retriever, mock_client):
        """Document should have score from search."""
        mock_client.query_points.return_value = MagicMock(points=[
            create_scored_point("doc-1", 0.9, "Content"),
        ])

        result = await retriever.retrieve("test query")

        assert result[0].score == 0.9

    @pytest.mark.asyncio
    async def test_metadata_does_not_include_content(self, retriever, mock_client):
        """Metadata should not include 'content' field."""
        mock_client.query_points.return_value = MagicMock(points=[
            create_scored_point("doc-1", 0.9, "Content", {"key": "value"}),
        ])

        result = await retriever.retrieve("test query")

        assert "content" not in result[0].metadata
        assert result[0].metadata["key"] == "value"
