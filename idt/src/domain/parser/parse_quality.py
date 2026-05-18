"""Domain value object for parse quality scoring.

파싱 결과 품질 점수 VO — 외부 의존 없음.
"""
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class ParseQualityScore:
    """파싱 결과 품질 점수."""

    page: int
    score: float
    text_char_count: int
    avg_word_length: float
    order_consistency: float
    issues: tuple[str, ...]

    FALLBACK_THRESHOLD: ClassVar[float] = 0.7

    def __post_init__(self) -> None:
        if not (0.0 <= self.score <= 1.0):
            raise ValueError("score must be between 0.0 and 1.0")
        if not (0.0 <= self.order_consistency <= 1.0):
            raise ValueError("order_consistency must be between 0.0 and 1.0")

    @property
    def fallback_required(self) -> bool:
        return self.score < self.FALLBACK_THRESHOLD
