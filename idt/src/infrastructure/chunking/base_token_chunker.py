"""Base token chunker utility for token-based text splitting."""
from typing import Dict, List, Any

import tiktoken

from src.domain.chunking.value_objects import ChunkingConfig


class BaseTokenChunker:
    """Base utility class for token-based text chunking.

    Provides common functionality for counting tokens, splitting text
    by token boundaries, and merging metadata.
    """

    def __init__(self, config: ChunkingConfig):
        """Initialize the chunker with configuration.

        Args:
            config: ChunkingConfig with chunk_size, overlap, and encoding model.
        """
        self.config = config
        self._encoder = tiktoken.get_encoding(config.encoding_model)

    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in text.

        Args:
            text: Text to count tokens for.

        Returns:
            Number of tokens.
        """
        if not text:
            return 0
        return len(self._encoder.encode(text))

    def split_by_tokens(self, text: str) -> List[str]:
        """Split text into chunks by token count with overlap.

        Args:
            text: Text to split into chunks.

        Returns:
            List of text chunks.
        """
        if not text:
            return []

        tokens = self._encoder.encode(text)
        total_tokens = len(tokens)

        if total_tokens <= self.config.chunk_size:
            return [text]

        chunks = []
        start = 0
        step = self.config.chunk_size - self.config.chunk_overlap

        while start < total_tokens:
            end = min(start + self.config.chunk_size, total_tokens)
            chunk_tokens = tokens[start:end]
            chunk_text = self._encoder.decode(chunk_tokens)
            chunks.append(chunk_text)

            if end >= total_tokens:
                break

            start += step

        return chunks

    def merge_metadata(
        self,
        original: Dict[str, Any],
        chunk_meta: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge original document metadata with chunk-specific metadata.

        Chunk metadata takes precedence on conflicts.

        Args:
            original: Original document metadata.
            chunk_meta: Chunk-specific metadata to add.

        Returns:
            Merged metadata dictionary.
        """
        result = dict(original)
        result.update(chunk_meta)
        return result
