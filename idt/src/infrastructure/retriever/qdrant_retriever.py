"""Qdrant retriever implementation.

Implements RetrieverInterface for Qdrant vector database.
"""
from typing import List, Optional, Tuple

from qdrant_client import AsyncQdrantClient

from src.domain.retriever.interfaces.retriever_interface import RetrieverInterface
from src.domain.retriever.value_objects.metadata_filter import MetadataFilter
from src.domain.vector.interfaces import EmbeddingInterface
from src.domain.vector.entities import Document
from src.domain.vector.value_objects import DocumentId


class QdrantRetriever(RetrieverInterface):
    """Qdrant implementation of RetrieverInterface.

    Provides document retrieval operations using Qdrant as the backend.
    Requires an EmbeddingInterface for text-to-vector conversion.
    """

    def __init__(
        self,
        client: AsyncQdrantClient,
        collection_name: str,
        embedding: EmbeddingInterface,
        score_threshold: Optional[float] = None,
    ) -> None:
        """Initialize QdrantRetriever.

        Args:
            client: Async Qdrant client
            collection_name: Name of the Qdrant collection
            embedding: Embedding interface for text conversion
            score_threshold: Optional minimum similarity score (0-1)
        """
        self._client = client
        self._collection_name = collection_name
        self._embedding = embedding
        self._score_threshold = score_threshold

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[MetadataFilter] = None,
    ) -> List[Document]:
        """Retrieve documents similar to the query.

        Args:
            query: The search query text
            top_k: Maximum number of documents to return (default: 10)
            filters: Optional metadata filters to apply

        Returns:
            List of documents sorted by relevance
        """
        results_with_scores = await self.retrieve_with_scores(query, top_k, filters)
        return [doc for doc, _ in results_with_scores]

    async def retrieve_with_scores(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[MetadataFilter] = None,
    ) -> List[Tuple[Document, float]]:
        """Retrieve documents with similarity scores.

        Args:
            query: The search query text
            top_k: Maximum number of documents to return (default: 10)
            filters: Optional metadata filters to apply

        Returns:
            List of (document, score) tuples sorted by score descending
        """
        query_vector = await self._embedding.embed_text(query)

        query_filter = None
        if filters is not None:
            query_filter = filters.to_qdrant_filter()

        results = await self._client.search(
            collection_name=self._collection_name,
            query_vector=query_vector,
            limit=top_k,
            query_filter=query_filter,
            with_vectors=True,
        )

        documents_with_scores: List[Tuple[Document, float]] = []
        for point in results:
            if self._score_threshold is not None and point.score < self._score_threshold:
                continue

            doc = self._point_to_document(point)
            documents_with_scores.append((doc, point.score))

        return documents_with_scores

    async def retrieve_by_metadata(
        self,
        filters: MetadataFilter,
        top_k: int = 10,
    ) -> List[Document]:
        """Retrieve documents by metadata filters only (no vector search).

        Uses Qdrant scroll API for metadata-only retrieval.

        Args:
            filters: Metadata filters to match documents
            top_k: Maximum number of documents to return (default: 10)

        Returns:
            List of documents matching the filters
        """
        scroll_filter = filters.to_qdrant_filter()

        records, _ = await self._client.scroll(
            collection_name=self._collection_name,
            scroll_filter=scroll_filter,
            limit=top_k,
            with_vectors=True,
        )

        return [self._record_to_document(record) for record in records]

    def get_retriever_name(self) -> str:
        """Get the name of this retriever implementation.

        Returns:
            Name identifying this retriever
        """
        return "qdrant-retriever"

    def _point_to_document(self, point) -> Document:
        """Convert Qdrant ScoredPoint to Document.

        Args:
            point: Qdrant ScoredPoint from search

        Returns:
            Document entity
        """
        payload = dict(point.payload) if point.payload else {}
        content = payload.pop("content", "")

        metadata = {k: str(v) for k, v in payload.items()}

        return Document(
            id=DocumentId(str(point.id)),
            content=content,
            vector=list(point.vector) if point.vector else [],
            metadata=metadata,
            score=point.score if hasattr(point, "score") else None,
        )

    def _record_to_document(self, record) -> Document:
        """Convert Qdrant Record to Document.

        Args:
            record: Qdrant Record from scroll

        Returns:
            Document entity
        """
        payload = dict(record.payload) if record.payload else {}
        content = payload.pop("content", "")

        metadata = {k: str(v) for k, v in payload.items()}

        return Document(
            id=DocumentId(str(record.id)),
            content=content,
            vector=list(record.vector) if record.vector else [],
            metadata=metadata,
            score=None,
        )
