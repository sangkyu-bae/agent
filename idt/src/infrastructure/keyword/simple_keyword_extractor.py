"""Frequency-based keyword extractor using regex tokenization.

외부 NLP 라이브러리 없이 정규식으로 한국어/영어 키워드를 추출한다.
"""
import re
from collections import Counter

from src.domain.keyword.interfaces import KeywordExtractorInterface
from src.domain.keyword.schemas import KeywordExtractionResult

# 영어 불용어 (단음절, 관사, 전치사, 접속사 등)
_ENGLISH_STOPWORDS: frozenset[str] = frozenset({
    "the", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "not", "only", "own",
    "same", "than", "too", "very", "just", "now", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "up", "about", "into",
    "and", "but", "or", "nor", "so", "yet", "if", "as", "it", "its",
    "this", "that", "these", "those", "he", "she", "we", "they", "you",
    "me", "him", "her", "us", "them", "my", "his", "our", "your", "their",
})


def _tokenize(text: str) -> list[str]:
    """정규식으로 한국어(2자↑) + 영어(2자↑) 토큰 추출."""
    tokens = re.findall(r"[가-힣]{2,}|[a-zA-Z]{2,}", text)
    return [t.lower() for t in tokens]


class SimpleKeywordExtractor(KeywordExtractorInterface):
    """빈도 기반 키워드 추출기 (외부 의존성 없음)."""

    def extract(self, text: str, top_n: int = 10) -> KeywordExtractionResult:
        """텍스트에서 상위 top_n 키워드를 빈도 기반으로 추출한다."""
        if not text or not text.strip():
            return KeywordExtractionResult(keywords=[], keyword_frequencies={})

        tokens = _tokenize(text)
        filtered = [t for t in tokens if t not in _ENGLISH_STOPWORDS]

        if not filtered:
            return KeywordExtractionResult(keywords=[], keyword_frequencies={})

        freq = Counter(filtered)
        top_items = freq.most_common(top_n)
        keywords = [word for word, _ in top_items]

        return KeywordExtractionResult(
            keywords=keywords,
            keyword_frequencies=dict(freq),
        )
