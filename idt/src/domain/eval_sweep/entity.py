"""모델 스윕 엔티티.

Design Ref: §3.1 — EvaluationSweep(실험 1건) / SweepRow(모델별 집계 VO).
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

SweepStatus = str  # pending | running | completed | failed


@dataclass
class EvaluationSweep:
    """모델 스윕 = 동일 에이전트를 여러 LLM 모델로 평가한 실험 1건.

    judge / temperature / model_ids / metrics는 **실행 시점 스냅샷**이다.
    나중에 모델 레지스트리나 에이전트 설정이 바뀌어도 이 실험의 조건은
    변하지 않아야 재현·비교가 성립한다 (Design D3).
    """

    id: str
    name: str
    agent_id: str
    testset_id: str
    judge_llm_model_id: str | None
    model_ids: list[str]
    metrics: list[str]
    created_at: datetime
    temperature: float = 0.0
    status: SweepStatus = "pending"
    total_runs: int = 0
    completed_runs: int = 0
    estimated_cost_usd: Decimal | None = None
    user_id: str | None = None
    error_message: str | None = None
    completed_at: datetime | None = None

    def mark_running(self) -> None:
        self.status = "running"

    def mark_run_completed(self, at: datetime) -> None:
        """하위 run 1건이 끝났다. 전부 끝나면 스윕도 완료 처리한다.

        개별 run의 성패는 여기서 따지지 않는다 — 실패한 모델도 '그 모델에 대한
        평가 결과'로서 매트릭스에 남아야 하기 때문이다 (Design D12).
        """
        self.completed_runs += 1
        if self.completed_runs >= self.total_runs:
            self.status = "completed"
            self.completed_at = at

    def mark_failed(self, message: str, at: datetime) -> None:
        """스윕 수준 실패 — 개별 run 실패가 아니라 오케스트레이션 자체가 깨진 경우."""
        self.status = "failed"
        self.error_message = message
        self.completed_at = at

    @property
    def progress_ratio(self) -> float:
        if self.total_runs <= 0:
            return 0.0
        return self.completed_runs / self.total_runs


@dataclass
class SweepRow:
    """매트릭스 한 행 = 모델 1개의 4축 집계 결과 (Design §4.2 rows[]).

    측정 불가 지표는 None이다 — 0.0("측정했고 0점")과 반드시 구분한다 (§3.5).
    """

    run_id: str
    llm_model_id: str | None
    status: str
    quality: dict[str, float | None] = field(default_factory=dict)
    cost_usd: Decimal | None = None
    latency_p50_ms: int | None = None
    latency_p95_ms: int | None = None
    tool_f1: float | None = None
    measured_cases: int = 0
    failed_cases: int = 0
    error_message: str | None = None
