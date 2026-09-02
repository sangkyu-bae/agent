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
    user_id: str | None = None  # NULL=소유권 도입(V055) 이전 레거시 — admin만 열람
    # agent-model-benchmark §3.3(V068): 모델 차원. NULL이면 단독 실행(기존 배치 평가).
    sweep_id: str | None = None
    llm_model_id: str | None = None
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
    # agent-model-benchmark §3.5: 측정 불가 지표는 None(N/A) — 0.0("측정했고 0점")과
    # 구분해야 집계 시 분모에서 뺄 수 있다.
    metrics: dict[str, float | None] = field(default_factory=dict)
    # D10: ai_run 조인 키 (토큰·비용·지연 회수). FK는 걸지 않는다(D11).
    ai_run_id: str | None = None
    # D6: 실제 호출된 도구 — expected_tools와 집합 비교해 F1을 낸다.
    tools_used: list[str] | None = None
