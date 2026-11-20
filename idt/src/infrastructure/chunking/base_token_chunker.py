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

        # Design Ref: answer-citation-verification FR-01 — 토큰 경계를 그대로 decode 하면
        # 한글 한 글자가 두 토큰에 걸칠 때 양쪽 청크에 U+FFFD 가 생긴다.
        # 경계를 UTF-8 글자 경계로 맞춘 뒤 바이트를 잘라 decode 한다.
        data = text.encode("utf-8")
        offsets = self._byte_offsets(tokens)
        if offsets[-1] != len(data):  # 방어: 토큰 바이트 합이 원문과 다르면 기존 방식
            return self._split_by_raw_tokens(tokens)

        chunks = []
        size = self.config.chunk_size
        step = size - self.config.chunk_overlap
        start, prev_end = 0, 0
        while start < total_tokens:
            s = min(self._snap(offsets, data, start, -1), prev_end)
            e = total_tokens
            if start + size < total_tokens:
                e = self._snap(offsets, data, min(s + size, total_tokens), -1)
                if e <= s:  # 한 글자가 청크 크기보다 많은 토큰 — 앞으로 넓힌다
                    e = self._snap(offsets, data, s + 1, 1)
            chunks.append(data[offsets[s]:offsets[e]].decode("utf-8"))
            if e >= total_tokens:
                break
            prev_end = e
            start += step

        return chunks

    def _byte_offsets(self, tokens: List[int]) -> List[int]:
        """토큰 i 의 시작 바이트 위치 (길이 len(tokens)+1, 마지막은 전체 바이트 수)."""
        offsets = [0]
        for token in tokens:
            offsets.append(offsets[-1] + len(self._encoder.decode_single_token_bytes(token)))
        return offsets

    @staticmethod
    def _snap(offsets: List[int], data: bytes, index: int, direction: int) -> int:
        """index 를 direction(-1 뒤로 / 1 앞으로) 방향의 가장 가까운 글자 경계 토큰으로."""
        last = len(offsets) - 1
        while 0 < index < last and (data[offsets[index]] & 0xC0) == 0x80:
            index += direction
        return index

    def _split_by_raw_tokens(self, tokens: List[int]) -> List[str]:
        """방어용 기존 동작 — 토큰 바이트가 원문과 맞지 않을 때만."""
        chunks = []
        step = self.config.chunk_size - self.config.chunk_overlap
        start = 0
        while start < len(tokens):
            end = min(start + self.config.chunk_size, len(tokens))
            chunks.append(self._encoder.decode(tokens[start:end]))
            if end >= len(tokens):
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
