"""Analysis policy for Excel Analysis Agent.

재시도 정책과 품질 임계값을 정의합니다.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AnalysisRetryPolicy:
    """분석 재시도 정책."""

    max_retries: int = 3
    retry_on_hallucination: bool = True
    require_web_search_on_retry: bool = True

    def should_retry(self, attempt: int, has_hallucination: bool) -> bool:
        """재시도 여부 판단."""
        if attempt >= self.max_retries:
            
            return False
        return has_hallucination and self.retry_on_hallucination

    def validate(self) -> None:
        """정책 유효성 검증."""
        if self.max_retries < 1 or self.max_retries > 5:
            raise ValueError("max_retries must be between 1 and 5")


@dataclass(frozen=True)
class AnalysisQualityThreshold:
    """분석 품질 임계값."""

    min_confidence_score: float = 0.7
    max_hallucination_score: float = 0.3

    def is_acceptable(self, confidence: float, hallucination: float) -> bool:
        """품질 기준 충족 여부."""
        return (
            confidence >= self.min_confidence_score
            and hallucination <= self.max_hallucination_score
        )

    def validate(self) -> None:
        """임계값 유효성 검증."""
        if not (0 <= self.min_confidence_score <= 1):
            raise ValueError("min_confidence_score must be between 0 and 1")
        if not (0 <= self.max_hallucination_score <= 1):
            raise ValueError("max_hallucination_score must be between 0 and 1")


AnalysisStatus = Literal[
    "pending",
    "analyzing",
    "verifying",
    "retrying",
    "code_executing",
    "completed",
    "failed",
]
