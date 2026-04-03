"""Interfaces for document chunking strategies."""
from abc import ABC, abstractmethod
from typing import List
from langchain_core.documents import Document


class ChunkingStrategy(ABC):
    """Abstract base class for chunking strategies.

    All chunking strategies must implement this interface to ensure
    consistent behavior across different chunking approaches.
    """

    @abstractmethod
    def chunk(self, documents: List[Document]) -> List[Document]:
        """Split documents into chunks.

        Args:
            documents: List of LangChain Documents to chunk.

        Returns:
            List of chunked Documents with updated metadata.
        """
        pass

    @abstractmethod
    def get_strategy_name(self) -> str:
        """Get the name of this chunking strategy.

        Returns:
            Strategy name as string.
        """
        pass

    @abstractmethod
    def get_chunk_size(self) -> int:
        """Get the chunk size used by this strategy.

        Returns:
            Chunk size in tokens.
        """
        pass
