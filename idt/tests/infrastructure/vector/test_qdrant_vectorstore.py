"""Tests for QdrantVectorStore implementation.

Infrastructure tests use mocks as per CLAUDE.md rules.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from typing import List
import uuid

from src.infrastructure.vector.qdrant_vectorstore import QdrantVectorStore
from src.domain.vector.interfaces import VectorStoreInterface, EmbeddingInterface
from src.domain.vector.entities import Document
from src.domain.vector.value_objects import (
    DocumentId,
    DocumentType,
    DateRange,
    SearchFilter,
)
from datetime import date


class TestQdrantVectorStore:
    """Tests for QdrantVectorStore implementation."""

    @pytest.fixture
    def mock_qdrant_client(self) -> MagicMock:
        """Create a mock Qdrant client."""
        client = MagicMock()
        client.upsert = AsyncMock()
        client.search = AsyncMock(return_value=[])
        client.delete = AsyncMock()
        client.retrieve = AsyncMock(return_value=[])
        # 컬렉션 관련 (기본: 컬렉션 이미 존재)
        existing_collection = MagicMock()
        existing_collection.name = "test"
        mock_collections = MagicMock()
        mock_collections.collections = [existing_collection]
        client.get_collections = AsyncMock(return_value=mock_collections)
        client.create_collection = AsyncMock()
        return client

    @pytest.fixture
    def mock_embedding(self) -> MagicMock:
        """Create a mock embedding interface."""
        embedding = MagicMock(spec=EmbeddingInterface)
        embedding.embed_text = AsyncMock(return_value=[0.1] * 1536)
        embedding.embed_documents = AsyncMock(return_value=[[0.1] * 1536])
        embedding.get_dimension.return_value = 1536
        return embedding

    def test_implements_vectorstore_interface(
        self, mock_qdrant_client: MagicMock, mock_embedding: MagicMock
    ) -> None:
        """QdrantVectorStore should implement VectorStoreInterface."""
        store = QdrantVectorStore(
            client=mock_qdrant_client,
            embedding=mock_embedding,
            collection_name="test",
        )
        assert isinstance(store, VectorStoreInterface)

    @pytest.mark.asyncio
    async def test_add_documents_returns_ids(
        self, mock_qdrant_client: MagicMock, mock_embedding: MagicMock
    ) -> None:
        """add_documents should return list of DocumentIds."""
        store = QdrantVectorStore(
            client=mock_qdrant_client,
            embedding=mock_embedding,
            collection_name="test",
        )

        doc = Document(
            id=None,
            content="Test content",
            vector=[0.1] * 1536,
            metadata={"type": "policy"},
        )

        with patch("src.infrastructure.vector.qdrant_vectorstore.uuid4") as mock_uuid:
            mock_uuid.return_value = uuid.UUID("12345678-1234-5678-1234-567812345678")
            result = await store.add_documents([doc])

        assert len(result) == 1
        assert isinstance(result[0], DocumentId)
        assert result[0].value == "12345678-1234-5678-1234-567812345678"

    @pytest.mark.asyncio
    async def test_add_documents_preserves_existing_id(
        self, mock_qdrant_client: MagicMock, mock_embedding: MagicMock
    ) -> None:
        """add_documents should preserve existing document IDs."""
        store = QdrantVectorStore(
            client=mock_qdrant_client,
            embedding=mock_embedding,
            collection_name="test",
        )

        doc_id = DocumentId("existing-id-123")
        doc = Document(
            id=doc_id,
            content="Test content",
            vector=[0.1] * 1536,
            metadata={},
        )

        result = await store.add_documents([doc])

        assert len(result) == 1
        assert result[0].value == "existing-id-123"

    @pytest.mark.asyncio
    async def test_add_documents_calls_qdrant_upsert(
        self, mock_qdrant_client: MagicMock, mock_embedding: MagicMock
    ) -> None:
        """add_documents should call Qdrant upsert."""
        store = QdrantVectorStore(
            client=mock_qdrant_client,
            embedding=mock_embedding,
            collection_name="test_collection",
        )

        doc = Document(
            id=None,
            content="Test content",
            vector=[0.1] * 1536,
            metadata={"type": "policy"},
        )

        await store.add_documents([doc])

        mock_qdrant_client.upsert.assert_called_once()
        call_args = mock_qdrant_client.upsert.call_args
        assert call_args.kwargs["collection_name"] == "test_collection"

    @pytest.mark.asyncio
    async def test_search_by_vector_returns_documents(
        self, mock_qdrant_client: MagicMock, mock_embedding: MagicMock
    ) -> None:
        """search_by_vector should return list of Documents."""
        mock_point = MagicMock()
        mock_point.id = "doc-123"
        mock_point.vector = [0.1] * 1536
        mock_point.payload = {"content": "Test content", "type": "policy"}
        mock_point.score = 0.95
        mock_qdrant_client.search = AsyncMock(return_value=[mock_point])

        store = QdrantVectorStore(
            client=mock_qdrant_client,
            embedding=mock_embedding,
            collection_name="test",
        )

        result = await store.search_by_vector(
            vector=[0.1] * 1536,
            top_k=10,
        )

        assert len(result) == 1
        assert isinstance(result[0], Document)
        assert result[0].id.value == "doc-123"
        assert result[0].score == 0.95

    @pytest.mark.asyncio
    async def test_search_by_text_embeds_and_searches(
        self, mock_qdrant_client: MagicMock, mock_embedding: MagicMock
    ) -> None:
        """search_by_text should embed text then search."""
        mock_point = MagicMock()
        mock_point.id = "doc-123"
        mock_point.vector = [0.1] * 1536
        mock_point.payload = {"content": "Test content"}
        mock_point.score = 0.9
        mock_qdrant_client.search = AsyncMock(return_value=[mock_point])

        store = QdrantVectorStore(
            client=mock_qdrant_client,
            embedding=mock_embedding,
            collection_name="test",
        )

        result = await store.search_by_text("search query", top_k=5)

        mock_embedding.embed_text.assert_called_once_with("search query")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_search_with_filter_document_type(
        self, mock_qdrant_client: MagicMock, mock_embedding: MagicMock
    ) -> None:
        """search should apply document_type filter."""
        mock_qdrant_client.search = AsyncMock(return_value=[])

        store = QdrantVectorStore(
            client=mock_qdrant_client,
            embedding=mock_embedding,
            collection_name="test",
        )

        search_filter = SearchFilter(document_type=DocumentType.POLICY)
        await store.search_by_vector(
            vector=[0.1] * 1536,
            top_k=10,
            filter=search_filter,
        )

        call_args = mock_qdrant_client.search.call_args
        assert call_args.kwargs.get("query_filter") is not None

    @pytest.mark.asyncio
    async def test_search_with_filter_metadata(
        self, mock_qdrant_client: MagicMock, mock_embedding: MagicMock
    ) -> None:
        """search should apply metadata filter."""
        mock_qdrant_client.search = AsyncMock(return_value=[])

        store = QdrantVectorStore(
            client=mock_qdrant_client,
            embedding=mock_embedding,
            collection_name="test",
        )

        search_filter = SearchFilter(metadata={"category": "finance"})
        await store.search_by_vector(
            vector=[0.1] * 1536,
            top_k=10,
            filter=search_filter,
        )

        call_args = mock_qdrant_client.search.call_args
        assert call_args.kwargs.get("query_filter") is not None

    @pytest.mark.asyncio
    async def test_delete_by_ids(
        self, mock_qdrant_client: MagicMock, mock_embedding: MagicMock
    ) -> None:
        """delete_by_ids should delete documents by their IDs."""
        mock_qdrant_client.delete = AsyncMock()

        store = QdrantVectorStore(
            client=mock_qdrant_client,
            embedding=mock_embedding,
            collection_name="test",
        )

        ids = [DocumentId("id-1"), DocumentId("id-2")]
        result = await store.delete_by_ids(ids)

        mock_qdrant_client.delete.assert_called_once()
        assert result == 2

    @pytest.mark.asyncio
    async def test_delete_by_metadata(
        self, mock_qdrant_client: MagicMock, mock_embedding: MagicMock
    ) -> None:
        """delete_by_metadata should delete documents matching criteria."""
        mock_qdrant_client.delete = AsyncMock()

        store = QdrantVectorStore(
            client=mock_qdrant_client,
            embedding=mock_embedding,
            collection_name="test",
        )

        result = await store.delete_by_metadata({"user_id": "user-123"})

        mock_qdrant_client.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_by_id_found(
        self, mock_qdrant_client: MagicMock, mock_embedding: MagicMock
    ) -> None:
        """get_by_id should return document if found."""
        mock_point = MagicMock()
        mock_point.id = "doc-123"
        mock_point.vector = [0.1] * 1536
        mock_point.payload = {"content": "Test content"}
        mock_qdrant_client.retrieve = AsyncMock(return_value=[mock_point])

        store = QdrantVectorStore(
            client=mock_qdrant_client,
            embedding=mock_embedding,
            collection_name="test",
        )

        result = await store.get_by_id(DocumentId("doc-123"))

        assert result is not None
        assert result.id.value == "doc-123"
        assert result.content == "Test content"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(
        self, mock_qdrant_client: MagicMock, mock_embedding: MagicMock
    ) -> None:
        """get_by_id should return None if not found."""
        mock_qdrant_client.retrieve = AsyncMock(return_value=[])

        store = QdrantVectorStore(
            client=mock_qdrant_client,
            embedding=mock_embedding,
            collection_name="test",
        )

        result = await store.get_by_id(DocumentId("nonexistent"))

        assert result is None

    @pytest.mark.asyncio
    async def test_default_top_k(
        self, mock_qdrant_client: MagicMock, mock_embedding: MagicMock
    ) -> None:
        """Default top_k should be 10."""
        mock_qdrant_client.search = AsyncMock(return_value=[])

        store = QdrantVectorStore(
            client=mock_qdrant_client,
            embedding=mock_embedding,
            collection_name="test",
        )

        await store.search_by_vector(vector=[0.1] * 1536)

        call_args = mock_qdrant_client.search.call_args
        assert call_args.kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_add_documents_creates_collection_if_not_exists(
        self, mock_qdrant_client: MagicMock, mock_embedding: MagicMock
    ) -> None:
        """add_documents should create collection if it doesn't exist."""
        # 컬렉션이 없는 상태
        mock_collections = MagicMock()
        mock_collections.collections = []
        mock_qdrant_client.get_collections = AsyncMock(return_value=mock_collections)
        mock_qdrant_client.create_collection = AsyncMock()

        store = QdrantVectorStore(
            client=mock_qdrant_client,
            embedding=mock_embedding,
            collection_name="new_collection",
        )

        doc = Document(
            id=None,
            content="Test content",
            vector=[0.1] * 1536,
            metadata={},
        )

        await store.add_documents([doc])

        mock_qdrant_client.create_collection.assert_called_once()
        call_args = mock_qdrant_client.create_collection.call_args
        assert call_args.kwargs["collection_name"] == "new_collection"

    @pytest.mark.asyncio
    async def test_add_documents_skips_creation_if_collection_exists(
        self, mock_qdrant_client: MagicMock, mock_embedding: MagicMock
    ) -> None:
        """add_documents should not create collection if it already exists."""
        # 컬렉션이 이미 있는 상태
        existing_collection = MagicMock()
        existing_collection.name = "existing_collection"
        mock_collections = MagicMock()
        mock_collections.collections = [existing_collection]
        mock_qdrant_client.get_collections = AsyncMock(return_value=mock_collections)
        mock_qdrant_client.create_collection = AsyncMock()

        store = QdrantVectorStore(
            client=mock_qdrant_client,
            embedding=mock_embedding,
            collection_name="existing_collection",
        )

        doc = Document(
            id=None,
            content="Test content",
            vector=[0.1] * 1536,
            metadata={},
        )

        await store.add_documents([doc])

        mock_qdrant_client.create_collection.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_collection_creates_with_correct_vector_size(
        self, mock_qdrant_client: MagicMock, mock_embedding: MagicMock
    ) -> None:
        """ensure_collection should create collection with correct vector size."""
        mock_collections = MagicMock()
        mock_collections.collections = []
        mock_qdrant_client.get_collections = AsyncMock(return_value=mock_collections)
        mock_qdrant_client.create_collection = AsyncMock()

        store = QdrantVectorStore(
            client=mock_qdrant_client,
            embedding=mock_embedding,
            collection_name="test_collection",
        )

        await store.ensure_collection(vector_size=768)

        mock_qdrant_client.create_collection.assert_called_once()
        call_args = mock_qdrant_client.create_collection.call_args
        vectors_config = call_args.kwargs["vectors_config"]
        assert vectors_config.size == 768

    @pytest.mark.asyncio
    async def test_add_documents_with_empty_list_does_not_create_collection(
        self, mock_qdrant_client: MagicMock, mock_embedding: MagicMock
    ) -> None:
        """add_documents with empty list should not create collection."""
        mock_qdrant_client.get_collections = AsyncMock()
        mock_qdrant_client.create_collection = AsyncMock()

        store = QdrantVectorStore(
            client=mock_qdrant_client,
            embedding=mock_embedding,
            collection_name="test",
        )

        result = await store.add_documents([])

        mock_qdrant_client.get_collections.assert_not_called()
        mock_qdrant_client.create_collection.assert_not_called()
        assert result == []
