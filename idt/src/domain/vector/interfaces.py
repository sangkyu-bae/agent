"""Domain interfaces for vector storage.

These are abstract base classes that define contracts for embeddings
and vector store operations. Implementations live in infrastructure layer.

No external API calls or LangChain usage allowed in domain layer.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from src.domain.vector.value_objects import DocumentId, SearchFilter
from src.domain.vector.entities import Document


class EmbeddingInterface(ABC):
    """Abstract interface for embedding operations.

    Implementations should wrap specific embedding models
    (e.g., OpenAI, HuggingFace) in the infrastructure layer.
    """

    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        """Generate an embedding vector for a single text.

        Args:
            text: The text to embed

        Returns:
            The embedding vector as a list of floats
        """
        pass

    @abstractmethod
    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Generate embedding vectors for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        """Return the dimension of vectors produced by this embedding model.

        Returns:
            The vector dimension (e.g., 1536 for text-embedding-3-small)
        """
        pass


class VectorStoreInterface(ABC):
    """Abstract interface for vector store operations.

    Implementations should wrap specific vector databases
    (e.g., Qdrant, Pinecone) in the infrastructure layer.
    """

    @abstractmethod
    async def add_documents(self, documents: List[Document]) -> List[DocumentId]:
        """Add documents to the vector store.

        Args:
            documents: List of documents with vectors to add

        Returns:
            List of DocumentIds assigned to the added documents
        """
        pass

    @abstractmethod
    async def search_by_vector(
        self,
        vector: List[float],
        top_k: int = 10,
        filter: Optional[SearchFilter] = None,
    ) -> List[Document]:
        """Search for similar documents using a vector.

        Args:
            vector: The query vector
            top_k: Maximum number of results to return (default: 10)
            filter: Optional filter conditions

        Returns:
            List of documents with similarity scores, sorted by relevance
        """
        pass

    @abstractmethod
    async def search_by_text(
        self,
        text: str,
        top_k: int = 10,
        filter: Optional[SearchFilter] = None,
    ) -> List[Document]:
        """Search for similar documents using text (will be embedded first).

        Args:
            text: The query text
            top_k: Maximum number of results to return (default: 10)
            filter: Optional filter conditions

        Returns:
            List of documents with similarity scores, sorted by relevance
        """
        pass

    @abstractmethod
    async def delete_by_ids(self, ids: List[DocumentId]) -> int:
        """Delete documents by their IDs.

        Args:
            ids: List of document IDs to delete

        Returns:
            Number of documents deleted
        """
        pass

    @abstractmethod
    async def delete_by_metadata(self, metadata_filter: Dict[str, str]) -> int:
        """Delete documents matching metadata criteria.

        Args:
            metadata_filter: Dictionary of metadata key-value pairs to match

        Returns:
            Number of documents deleted
        """
        pass

    @abstractmethod
    async def get_by_id(self, doc_id: DocumentId) -> Optional[Document]:
        """Retrieve a single document by its ID.

        Args:
            doc_id: The document ID to retrieve

        Returns:
            The document if found, None otherwise
        """
        pass
