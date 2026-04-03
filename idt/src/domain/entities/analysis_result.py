"""Analysis result entities for Excel Analysis Agent.

분석 시도 기록과 최종 분석 결과를 정의합니다.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class AnalysisAttempt:
    """단일 분석 시도 기록."""

    attempt_number: int
    analysis_text: str
    confidence_score: float
    hallucination_score: float
    used_web_search: bool
    timestamp: datetime
    error: Optional[str] = None


@dataclass
class AnalysisResult:
    """최종 분석 결과."""

    request_id: str
    user_query: str
    excel_summary: Dict[str, Any]
    final_answer: str
    is_successful: bool
    attempts: List[AnalysisAttempt]
    executed_code: Optional[str] = None
    code_output: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.utcnow())

    @property
    def total_attempts(self) -> int:
        return len(self.attempts)

    @property
    def final_quality_score(self) -> float:
        if not self.attempts:
            return 0.0
        last = self.attempts[-1]
        return last.confidence_score - last.hallucination_score
