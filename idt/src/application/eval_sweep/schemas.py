"""모델 스윕 요청/응답 DTO.

Design Ref: §4.2 — estimate / create / detail.
"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class SweepEstimateRequest(BaseModel):
    agent_id: str
    testset_id: str
    model_ids: list[str]
    judge_llm_model_id: str | None = None
    metrics: list[str] = Field(default_factory=list)


class PerModelEstimate(BaseModel):
    llm_model_id: str
    display_name: str
    estimated_cost_usd: Decimal


class SweepEstimateResponse(BaseModel):
    case_count: int
    model_count: int
    total_calls: int
    estimated_cost_usd: Decimal
    estimated_minutes: int
    basis: dict
    per_model: list[PerModelEstimate]


class CreateSweepRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    agent_id: str
    testset_id: str
    model_ids: list[str]
    judge_llm_model_id: str | None = None
    metrics: list[str] = Field(default_factory=list)


class CreateSweepResponse(BaseModel):
    sweep_id: str
    status: str
    total_runs: int
    estimated_cost_usd: Decimal | None
    message: str


class SweepRowResponse(BaseModel):
    run_id: str
    llm_model_id: str | None
    llm_model_name: str | None
    status: str
    quality: dict[str, float | None]
    cost_usd: Decimal | None
    latency_p50_ms: int | None
    latency_p95_ms: int | None
    tool_f1: float | None
    measured_cases: int
    failed_cases: int
    error_message: str | None = None


class SweepSummaryResponse(BaseModel):
    id: str
    name: str
    agent_id: str
    testset_id: str
    judge_llm_model_id: str | None
    temperature: float
    status: str
    total_runs: int
    completed_runs: int
    estimated_cost_usd: Decimal | None
    created_at: datetime
    completed_at: datetime | None


class SweepDetailResponse(SweepSummaryResponse):
    model_ids: list[str]
    metrics: list[str]
    rows: list[SweepRowResponse]
    # G-2: 어떤 조건의 실험이었는지 화면에서 알 수 있어야 재현성 스냅샷이 의미를 갖는다.
    agent_name: str | None = None
    testset_name: str | None = None
    case_count: int = 0
    # G-1: 실제 지출 합계. estimated_cost_usd와 대조해 추정 정확도를 확인한다
    # (Plan NFR "추정치가 실제의 ±30% 이내"를 측정할 유일한 수단).
    actual_cost_usd: Decimal | None = None
