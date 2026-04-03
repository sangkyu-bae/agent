"""DocumentCompressorInterface for abstracting document compression."""
from abc import ABC, abstractmethod
from typing import List

from langchain_core.documents import Document

from src.domain.compressor.entities.compressed_document import CompressedDocument


class DocumentCompressorInterface(ABC):
    """Abstract interface for document compressors.

    This interface defines the contract for compressors that filter
    documents based on relevance to a query.
    """

    @abstractmethod
    async def compress(
        self, documents: List[Document], query: str
    ) -> List[Document]:
        """Compress/filter documents based on relevance to query.

        Args:
            documents: List of documents to evaluate.
            query: The query to evaluate relevance against.

        Returns:
            List of documents that are relevant to the query.
        """
        pass

    @abstractmethod
    async def compress_with_scores(
        self, documents: List[Document], query: str
    ) -> List[CompressedDocument]:
        """Compress documents and return with relevance scores.

        Args:
            documents: List of documents to evaluate.
            query: The query to evaluate relevance against.

        Returns:
            List of CompressedDocument objects containing documents
            and their relevance evaluations.
        """
        pass

    @abstractmethod
    def get_compressor_name(self) -> str:
        """Get the name of the compressor.

        Returns:
            The compressor name identifier.
        """
        pass
