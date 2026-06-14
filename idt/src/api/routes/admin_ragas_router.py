"""Admin RAGAS 평가 대시보드 REST API 엔드포인트."""
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import require_role

router = APIRouter(prefix="/api/v1/admin/ragas", tags=["admin-ragas"])


# ── DI 플레이스홀더 ────────────────────────────────────────────────

def get_admin_eval_use_case():
    raise NotImplementedError("AdminEvalUseCase not initialized")


# ── Response 스키마 ─────────────────────────────────────────────────

class EvalRunSummaryBody(BaseModel):
    id: str
    eval_type: str
    target_type: str
    status: str
    total_cases: int
    created_at: datetime
    completed_at: datetime | None
    summary: dict[str, float]


class DashboardResponseBody(BaseModel):
    total_runs: int
    status_counts: dict[str, int]
    target_type_counts: dict[str, int]
    avg_metrics: dict[str, float]
    recent_runs: list[EvalRunSummaryBody]


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    limit: int
    offset: int


class EvalResultItemBody(BaseModel):
    id: str
    question: str
    answer: str
    ground_truth: str | None
    contexts: list[str] = Field(default_factory=list)
    scores: dict[str, float]
    created_at: datetime


class RunDetailResponseBody(BaseModel):
    id: str
    eval_type: str
    target_type: str
    status: str
    total_cases: int
    config: dict
    created_at: datetime
    completed_at: datetime | None
    summary: dict[str, float]
    results: list[EvalResultItemBody]
    results_total: int


class TestsetItemBody(BaseModel):
    id: str
    name: str
    description: str | None
    case_count: int
    created_at: datetime


# ── 엔드포인트 ──────────────────────────────────────────────────────

@router.get("/dashboard", response_model=DashboardResponseBody)
async def get_dashboard(
    recent_limit: int = Query(5, ge=1, le=20),
    admin: User = Depends(require_role("admin")),
    use_case=Depends(get_admin_eval_use_case),
) -> DashboardResponseBody:
    request_id = str(uuid.uuid4())
    stats = await use_case.get_dashboard_stats(recent_limit, request_id)
    return DashboardResponseBody(
        total_runs=stats.total_runs,
        status_counts=stats.status_counts,
        target_type_counts=stats.target_type_counts,
        avg_metrics=stats.avg_metrics,
        recent_runs=[
            EvalRunSummaryBody(
                id=r.id,
                eval_type=r.eval_type,
                target_type=r.target_type,
                status=r.status,
                total_cases=r.total_cases,
                created_at=r.created_at,
                completed_at=r.completed_at,
                summary=r.summary,
            )
            for r in stats.recent_runs
        ],
    )


@router.get("/runs", response_model=PaginatedResponse)
async def list_runs(
    target_type: str | None = Query(None),
    eval_type: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_role("admin")),
    use_case=Depends(get_admin_eval_use_case),
) -> PaginatedResponse:
    request_id = str(uuid.uuid4())
    items, total = await use_case.list_runs_with_summary(
        target_type, eval_type, status, limit, offset, request_id
    )
    return PaginatedResponse(
        items=[
            EvalRunSummaryBody(
                id=r.id,
                eval_type=r.eval_type,
                target_type=r.target_type,
                status=r.status,
                total_cases=r.total_cases,
                created_at=r.created_at,
                completed_at=r.completed_at,
                summary=r.summary,
            )
            for r in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/runs/{run_id}", response_model=RunDetailResponseBody)
async def get_run_detail(
    run_id: str,
    admin: User = Depends(require_role("admin")),
    use_case=Depends(get_admin_eval_use_case),
) -> RunDetailResponseBody:
    request_id = str(uuid.uuid4())
    detail = await use_case.get_run_with_results(run_id, request_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return RunDetailResponseBody(
        id=detail.id,
        eval_type=detail.eval_type,
        target_type=detail.target_type,
        status=detail.status,
        total_cases=detail.total_cases,
        config=detail.config,
        created_at=detail.created_at,
        completed_at=detail.completed_at,
        summary=detail.summary,
        results=[
            EvalResultItemBody(
                id=r.id,
                question=r.question,
                answer=r.answer,
                ground_truth=r.ground_truth,
                contexts=r.contexts,
                scores=r.scores,
                created_at=r.created_at,
            )
            for r in detail.results
        ],
        results_total=detail.results_total,
    )


@router.get("/testsets", response_model=PaginatedResponse)
async def list_testsets(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: User = Depends(require_role("admin")),
    use_case=Depends(get_admin_eval_use_case),
) -> PaginatedResponse:
    request_id = str(uuid.uuid4())
    items, total = await use_case.list_testsets(limit, offset, request_id)
    return PaginatedResponse(
        items=[
            TestsetItemBody(
                id=t["id"],
                name=t["name"],
                description=t.get("description"),
                case_count=t["case_count"],
                created_at=t["created_at"],
            )
            for t in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
