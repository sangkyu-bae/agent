"""Full token chunking strategy implementation."""
from typing import List

from langchain_core.documents import Document

from src.domain.chunking.interfaces import ChunkingStrategy
from src.domain.chunking.value_objects import ChunkingConfig
from src.infrastructure.chunking.base_token_chunker import BaseTokenChunker


class FullTokenStrategy(ChunkingStrategy):
    """Chunking strategy that splits documents by token count."""

    def __init__(self, config: ChunkingConfig):
        self._config = config
        self._chunker = BaseTokenChunker(config)

    def chunk(self, documents: List[Document]) -> List[Document]:
        """Split documents into token-based chunks."""
        if not documents:
            return []

        result = []
        for doc in documents:
            doc_chunks = self._chunk_document(doc)
            result.extend(doc_chunks)

        return result

    def _chunk_document(self, doc: Document) -> List[Document]:
        content = doc.page_content
        if not content:
            return []

        text_chunks = self._chunker.split_by_tokens(content)
        total_chunks = len(text_chunks)

        result = []
        for i, chunk_text in enumerate(text_chunks):
            chunk_metadata = self._chunker.merge_metadata(
                doc.metadata,
                {"chunk_type": "full", "chunk_index": i, "total_chunks": total_chunks},
            )
            result.append(Document(page_content=chunk_text, metadata=chunk_metadata))

        return result

    def get_strategy_name(self) -> str:
        return "full_token"

    def get_chunk_size(self) -> int:
        return self._config.chunk_size
