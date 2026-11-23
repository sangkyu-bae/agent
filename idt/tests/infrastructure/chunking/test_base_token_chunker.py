"""Tests for BaseTokenChunker infrastructure module."""
import pytest

from src.infrastructure.chunking.base_token_chunker import BaseTokenChunker
from src.domain.chunking.value_objects import ChunkingConfig


class TestBaseTokenChunker:
    """Tests for BaseTokenChunker utility class."""

    @pytest.fixture
    def chunker(self):
        """Create a BaseTokenChunker instance for testing."""
        config = ChunkingConfig(chunk_size=100, chunk_overlap=10)
        return BaseTokenChunker(config)

    @pytest.fixture
    def large_chunk_chunker(self):
        """Create a BaseTokenChunker with larger chunk size."""
        config = ChunkingConfig(chunk_size=1000, chunk_overlap=100)
        return BaseTokenChunker(config)

    def test_count_tokens_simple_text(self, chunker):
        """count_tokens should return accurate token count for simple text."""
        text = "Hello world"
        count = chunker.count_tokens(text)

        # cl100k_base encodes "Hello world" as 2 tokens
        assert count == 2

    def test_count_tokens_empty_string(self, chunker):
        """count_tokens should return 0 for empty string."""
        assert chunker.count_tokens("") == 0

    def test_count_tokens_longer_text(self, chunker):
        """count_tokens should handle longer text."""
        text = "The quick brown fox jumps over the lazy dog"
        count = chunker.count_tokens(text)

        # Verify it returns a positive number
        assert count > 0
        assert count == 9  # cl100k_base token count for this sentence

    def test_split_by_tokens_short_text(self, chunker):
        """split_by_tokens should not split text shorter than chunk_size."""
        text = "Hello world"  # 2 tokens, less than chunk_size=100
        chunks = chunker.split_by_tokens(text)

        assert len(chunks) == 1
        assert chunks[0] == text

    def test_split_by_tokens_exact_chunk_size(self, chunker):
        """split_by_tokens should handle text at exactly chunk_size."""
        # Create text of exactly 100 tokens
        # "word " is typically 1-2 tokens, so we'll use a repeating pattern
        words = ["token"] * 50  # Each "token" is 1 token in cl100k_base
        text = " ".join(words)

        chunks = chunker.split_by_tokens(text)

        # Should fit in one chunk since we're under 100 tokens
        assert len(chunks) >= 1

    def test_split_by_tokens_with_overlap(self, large_chunk_chunker):
        """split_by_tokens should apply overlap between chunks."""
        # Create text that will span multiple chunks
        # Using a pattern that gives us predictable token counts
        words = ["word"] * 2500  # Each "word" is 1 token
        text = " ".join(words)

        chunks = large_chunk_chunker.split_by_tokens(text)

        # Should have multiple chunks
        assert len(chunks) > 1

        # Verify overlap by checking token counts
        total_tokens = large_chunk_chunker.count_tokens(text)
        chunk_size = 1000
        overlap = 100
        effective_step = chunk_size - overlap

        # Calculate expected chunks (approximately)
        expected_min_chunks = total_tokens // effective_step
        assert len(chunks) >= expected_min_chunks - 1

    def test_split_by_tokens_preserves_text_content(self, chunker):
        """split_by_tokens should preserve all text content when rejoined."""
        text = "Hello world, this is a test."
        chunks = chunker.split_by_tokens(text)

        # For short text, there should be one chunk with exact content
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_split_by_tokens_multiple_chunks_cover_all_text(
        self, large_chunk_chunker
    ):
        """All original text should be covered by chunks."""
        words = ["testing"] * 3000
        text = " ".join(words)

        chunks = large_chunk_chunker.split_by_tokens(text)

        # First chunk should start at the beginning
        assert chunks[0].startswith("testing")

        # Last chunk should end with the same word
        assert chunks[-1].rstrip().endswith("testing")

    def test_merge_metadata_combines_dicts(self, chunker):
        """merge_metadata should combine original and chunk metadata."""
        original = {"document_id": "doc_123", "user_id": "user_456"}
        chunk_meta = {"chunk_index": 0, "total_chunks": 5}

        result = chunker.merge_metadata(original, chunk_meta)

        assert result["document_id"] == "doc_123"
        assert result["user_id"] == "user_456"
        assert result["chunk_index"] == 0
        assert result["total_chunks"] == 5

    def test_merge_metadata_chunk_overrides_original(self, chunker):
        """Chunk metadata should override original on conflict."""
        original = {"chunk_index": 99, "document_id": "doc_123"}
        chunk_meta = {"chunk_index": 0, "chunk_type": "full"}

        result = chunker.merge_metadata(original, chunk_meta)

        assert result["chunk_index"] == 0  # Overridden by chunk_meta
        assert result["document_id"] == "doc_123"  # Preserved
        assert result["chunk_type"] == "full"

    def test_merge_metadata_handles_empty_original(self, chunker):
        """merge_metadata should handle empty original metadata."""
        original = {}
        chunk_meta = {"chunk_type": "full", "chunk_index": 0}

        result = chunker.merge_metadata(original, chunk_meta)

        assert result == chunk_meta

    def test_merge_metadata_handles_empty_chunk_meta(self, chunker):
        """merge_metadata should handle empty chunk metadata."""
        original = {"document_id": "doc_123"}
        chunk_meta = {}

        result = chunker.merge_metadata(original, chunk_meta)

        assert result == original

    def test_config_is_stored(self, chunker):
        """BaseTokenChunker should store the config."""
        assert chunker.config.chunk_size == 100
        assert chunker.config.chunk_overlap == 10
        assert chunker.config.encoding_model == "cl100k_base"

    def test_different_encoding_model(self):
        """BaseTokenChunker should support different encoding models."""
        config = ChunkingConfig(
            chunk_size=100,
            chunk_overlap=10,
            encoding_model="p50k_base"
        )
        chunker = BaseTokenChunker(config)

        # Should not raise error and should work
        count = chunker.count_tokens("Hello world")
        assert count > 0


# answer-citation-verification FR-01 — 토큰 경계가 멀티바이트 글자 중간에 걸려도
# 깨진 문자(U+FFFD)를 만들지 않는다.
_KOREAN = (
    "가계대출 총량관리 목표를 경상성장률 이내로 관리하고, 수도권 주택담보대출 한도를 "
    "6억 원으로 제한합니다. 정책대출 공급 계획은 연간 25% 감축합니다. 뷁똠햏쌰 같은 "
    "드문 글자도 섞어 토큰 경계가 글자 가운데에 오도록 합니다. "
) * 12


class TestSplitByTokensMultibyteBoundary:
    @pytest.mark.parametrize("size,overlap", [(7, 2), (13, 3), (31, 5), (50, 10)])
    def test_no_replacement_char_in_korean_chunks(self, size, overlap):
        chunker = BaseTokenChunker(ChunkingConfig(chunk_size=size, chunk_overlap=overlap))
        chunks = chunker.split_by_tokens(_KOREAN)
        assert len(chunks) > 1
        assert all("�" not in c for c in chunks)

    @pytest.mark.parametrize("size,overlap", [(7, 2), (13, 3), (31, 5)])
    def test_chunks_stay_within_token_limit(self, size, overlap):
        chunker = BaseTokenChunker(ChunkingConfig(chunk_size=size, chunk_overlap=overlap))
        for chunk in chunker.split_by_tokens(_KOREAN):
            assert chunker.count_tokens(chunk) <= size + 1  # 재인코딩 병합 오차 1 허용

    @pytest.mark.parametrize("size,overlap", [(7, 2), (13, 3)])
    def test_chunks_are_substrings_and_cover_text(self, size, overlap):
        chunker = BaseTokenChunker(ChunkingConfig(chunk_size=size, chunk_overlap=overlap))
        chunks = chunker.split_by_tokens(_KOREAN)
        assert all(c in _KOREAN for c in chunks)
        assert _KOREAN.startswith(chunks[0])
        assert _KOREAN.endswith(chunks[-1])
        # 다음 청크 시작이 이전 청크 끝을 넘지 않는다 → 빠진 글자 없음
        pos = 0
        for c in chunks:
            start = _KOREAN.find(c, max(0, pos - len(c)))
            assert start <= pos
            pos = start + len(c)
        assert pos == len(_KOREAN)

    def test_original_replacement_char_is_kept(self):
        text = "원문에 이미 � 가 있는 문장입니다. " * 30
        chunker = BaseTokenChunker(ChunkingConfig(chunk_size=11, chunk_overlap=2))
        joined = "".join(chunker.split_by_tokens(text))
        assert "�" in joined

    def test_ascii_split_unchanged(self):
        text = "The quick brown fox jumps over the lazy dog. " * 40
        chunker = BaseTokenChunker(ChunkingConfig(chunk_size=20, chunk_overlap=4))
        enc = chunker._encoder
        tokens = enc.encode(text)
        expected, start = [], 0
        while start < len(tokens):
            end = min(start + 20, len(tokens))
            expected.append(enc.decode(tokens[start:end]))
            if end >= len(tokens):
                break
            start += 16
        assert chunker.split_by_tokens(text) == expected
