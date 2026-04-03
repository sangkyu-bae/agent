"""Semantic chunking strategy based on paragraph boundary detection."""
import re
from typing import List, Tuple

from langchain_core.documents import Document

from src.domain.chunking.interfaces import ChunkingStrategy
from src.domain.chunking.value_objects import ChunkingConfig
from src.infrastructure.chunking.base_token_chunker import BaseTokenChunker


class SemanticStrategy(ChunkingStrategy):
    """Chunking strategy that splits documents at semantic paragraph boundaries.

    Splitting priority:
    1. Paragraph boundaries (\\n\\n)
    2. Token-based split for paragraphs exceeding max_chunk_size
    3. Merging of paragraphs shorter than min_chunk_size
    """

    def __init__(self, config: ChunkingConfig, min_chunk_size: int = 200):
        """Initialize the strategy.

        Args:
            config: ChunkingConfig where chunk_size acts as the max chunk size.
            min_chunk_size: Minimum token count per chunk before merging.
        """
        self._config = config
        self._min_chunk_size = min_chunk_size
        self._chunker = BaseTokenChunker(config)

    def chunk(self, documents: List[Document]) -> List[Document]:
        """Split documents using semantic paragraph boundaries."""
        if not documents:
            return []

        result = []
        for doc in documents:
            result.extend(self._chunk_document(doc))
        return result

    def _chunk_document(self, doc: Document) -> List[Document]:
        content = doc.page_content
        if not content:
            return []

        segments = self._build_segments(content)
        merged = self._merge_short_segments(segments)

        total = len(merged)
        return [
            Document(
                page_content=text,
                metadata=self._chunker.merge_metadata(
                    doc.metadata,
                    {
                        "chunk_type": "semantic",
                        "semantic_boundary": boundary,
                        "chunk_index": idx,
                        "total_chunks": total,
                    },
                ),
            )
            for idx, (text, boundary) in enumerate(merged)
        ]

    def _build_segments(self, content: str) -> List[Tuple[str, str]]:
        """Split content into (text, boundary_type) segments."""
        paragraphs = [p.strip() for p in re.split(r"\n\n+", content) if p.strip()]

        if not paragraphs:
            return [(content.strip(), "full")]

        segments: List[Tuple[str, str]] = []
        for para in paragraphs:
            if self._chunker.count_tokens(para) > self._config.chunk_size:
                for sub in self._chunker.split_by_tokens(para):
                    segments.append((sub, "token"))
            else:
                segments.append((para, "paragraph"))

        return segments

    def _merge_short_segments(
        self, segments: List[Tuple[str, str]]
    ) -> List[Tuple[str, str]]:
        """Merge adjacent segments that are shorter than min_chunk_size."""
        if not segments:
            return []

        merged: List[Tuple[str, str]] = []
        current_text, current_boundary = segments[0]

        for text, boundary in segments[1:]:
            if self._chunker.count_tokens(current_text) < self._min_chunk_size:
                current_text = current_text + "\n\n" + text
            else:
                merged.append((current_text, current_boundary))
                current_text, current_boundary = text, boundary

        merged.append((current_text, current_boundary))
        return merged

    def get_strategy_name(self) -> str:
        return "semantic"

    def get_chunk_size(self) -> int:
        return self._config.chunk_size
