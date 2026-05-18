"""RAGAS 평가 도메인 엔티티."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

EvalType = Literal["batch", "realtime"]
TargetType = Literal["rag", "agent", "retrieval"]
RunStatus = Literal["pending", "running", "completed", "failed"]


@dataclass
class EvaluationRun:
    """평가 실행 단위."""

    id: str
    eval_type: EvalType
    target_type: TargetType
    status: RunStatus
    total_cases: int
    created_at: datetime
    target_id: str | None = None
    config: dict = field(default_factory=dict)
    completed_at: datetime | None = None
    error_message: str | None = None

    def mark_completed(self, completed_at: datetime) -> None:
        self.status = "completed"
        self.completed_at = completed_at

    def mark_failed(self, error_message: str, failed_at: datetime) -> None:
        self.status = "failed"
        self.error_message = error_message
        self.completed_at = failed_at


@dataclass
class EvaluationResult:
    """개별 질문-답변 쌍의 평가 결과."""

    id: str
    run_id: str
    question: str
    answer: str
    contexts: list[str]
    created_at: datetime
    ground_truth: str | None = None
    metrics: dict[str, float] = field(default_factory=dict)
