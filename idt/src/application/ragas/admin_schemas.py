"""Admin RAGAS 평가 대시보드 Application DTO."""
from dataclasses import dataclass, field
from datetime import datetime

from src.application.ragas.schemas import EvalResultItem, EvalRunDetailResponse


@dataclass(frozen=True)
class DashboardStatsResponse:
    total_runs: int
    status_counts: dict[str, int]
    target_type_counts: dict[str, int]
    avg_metrics: dict[str, float]
    recent_runs: list[EvalRunDetailResponse]


@dataclass(frozen=True)
class RunWithResultsResponse:
    id: str
    eval_type: str
    target_type: str
    status: str
    total_cases: int
    config: dict
    created_at: datetime
    completed_at: datetime | None
    summary: dict[str, float]
    results: list[EvalResultItem]
    results_total: int
