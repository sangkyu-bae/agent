"""ChunkingService: facade that adds logging around a ChunkingStrategy."""
from typing import List

from langchain_core.documents import Document

from src.domain.chunking.interfaces import ChunkingStrategy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ChunkingService:
    """Orchestrates chunking with logging and error handling.

    Receives a pre-built ChunkingStrategy and delegates chunk() to it,
    adding structured logging around the call.
    """

    def __init__(self, logger: LoggerInterface) -> None:
        self._logger = logger

    def chunk_documents(
        self,
        documents: List[Document],
        strategy: ChunkingStrategy,
    ) -> List[Document]:
        """Chunk documents using the given strategy.

        Args:
            documents: Source documents to chunk.
            strategy: Chunking strategy instance to delegate to.

        Returns:
            List of chunked Documents.

        Raises:
            Exception: Re-raises any exception from the strategy after logging.
        """
        self._logger.info(
            "Chunking started",
            strategy=strategy.get_strategy_name(),
            doc_count=len(documents),
        )

        try:
            result = strategy.chunk(documents)
        except Exception as exc:
            self._logger.error("Chunking failed", exception=exc)
            raise

        self._logger.info("Chunking completed", chunk_count=len(result))
        return result
