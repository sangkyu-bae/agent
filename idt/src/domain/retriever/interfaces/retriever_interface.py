"""RetrieverInterface abstract base class.

Defines the contract for document retrieval implementations.
No external API calls allowed in domain layer.
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from src.domain.retriever.value_objects.metadata_filter import MetadataFilter
from src.domain.vector.entities import Document


class RetrieverInterface(ABC):
    """Abstract interface for document retrieval operations.

    Implementations should wrap specific retrieval backends
    (e.g., Qdrant, Pinecone) in the infrastructure layer.

    All retrieve methods are async to support non-blocking I/O.
    """

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    async def retrieve_by_metadata(
        self,
        filters: MetadataFilter,
        top_k: int = 10,
    ) -> List[Document]:
        """Retrieve documents by metadata filters only (no vector search).

        Args:
            filters: Metadata filters to match documents
            top_k: Maximum number of documents to return (default: 10)

        Returns:
            List of documents matching the filters
        """
        pass

    @abstractmethod
    def get_retriever_name(self) -> str:
        """Get the name of this retriever implementation.

        Returns:
            Name identifying this retriever (e.g., "qdrant-retriever")
        """
        pass
