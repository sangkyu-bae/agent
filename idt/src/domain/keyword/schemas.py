"""Keyword extraction domain schemas."""
from dataclasses import dataclass, field


@dataclass
class KeywordExtractionResult:
    """키워드 추출 결과."""

    keywords: list[str]
    keyword_frequencies: dict[str, int]
