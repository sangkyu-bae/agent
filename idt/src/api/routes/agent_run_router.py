"""Agent Run observability router (M4 + M5 dashboard).

Endpoints:
- GET  /api/v1/agents/runs/{run_id}           — run 상세 트리
- GET  /api/v1/admin/runs                     — Run 목록 (★ M5)
- GET  /api/v1/admin/usage/users              — 사용자별 집계
- GET  /api/v1/admin/usage/llm-models         — LLM 모델별 집계
- GET  /api/v1/admin/usage/by-node            — 노드별 집계 (★ M3 효과)
- GET  /api/v1/admin/usage/summary            — 대시보드 카드 4종 (★ M5)
- GET  /api/v1/admin/usage/timeseries         — 일자별 시계열 (★ M5)
- GET  /api/v1/usage/me                       — 본인 사용량
- GET  /api/v1/usage/me/runs                  — 본인 Run 목록 (★ M5)
- GET  /api/v1/usage/me/timeseries            — 본인 일자별 시계열 (★ M5)
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.agent_run.exceptions import (
    RunAccessDeniedError,
    RunNotFoundError,
)
from src.application.agent_run.use_cases.get_my_usage_timeseries_use_case import (
    GetMyUsageTimeseriesUseCase,
)
from src.application.agent_run.use_cases.get_run_detail_use_case import (
    GetRunDetailUseCase,
)
from src.application.agent_run.use_cases.get_usage_by_llm_use_case import (
    GetUsageByLlmUseCase,
)
from src.application.agent_run.use_cases.get_usage_by_node_use_case import (
    GetUsageByNodeUseCase,
)
from src.application.agent_run.use_cases.get_usage_by_user_use_case import (
    GetUsageByUserUseCase,
)
from src.application.agent_run.use_cases.get_usage_me_use_case import (
    GetUsageMeUseCase,
)
from src.application.agent_run.use_cases.get_usage_summary_use_case import (
    GetUsageSummaryUseCase,
)
from src.application.agent_run.use_cases.get_usage_timeseries_use_case import (
    GetUsageTimeseriesUseCase,
)
from src.application.agent_run.use_cases.list_my_runs_use_case import (
    ListMyRunsUseCase,
)
from src.application.agent_run.use_cases.list_runs_use_case import (
    ListRunsUseCase,
)
from src.domain.agent_run.interfaces import RunListFilters
from src.domain.auth.entities import User, UserRole
from src.interfaces.dependencies.auth import get_current_user, require_role
from src.interfaces.schemas.agent_run_response import (
    RunDetailResponse,
    RunListResponse,
    UsageByLlmResponse,
    UsageByNodeResponse,
    UsageByUserResponse,
    UsageSummaryResponse,
    UsageTimeseriesResponse,
)


router = APIRouter(prefix="/api/v1", tags=["agent-run-observability"])


# -------- DI placeholders (override in create_app) --------


def get_run_detail_use_case() -> GetRunDetailUseCase:
    raise NotImplementedError("GetRunDetailUseCase not initialized")


def get_usage_by_user_use_case() -> GetUsageByUserUseCase:
    raise NotImplementedError("GetUsageByUserUseCase not initialized")


def get_usage_by_llm_use_case() -> GetUsageByLlmUseCase:
    raise NotImplementedError("GetUsageByLlmUseCase not initialized")


def get_usage_by_node_use_case() -> GetUsageByNodeUseCase:
    raise NotImplementedError("GetUsageByNodeUseCase not initialized")


def get_usage_me_use_case() -> GetUsageMeUseCase:
    raise NotImplementedError("GetUsageMeUseCase not initialized")


def get_list_runs_use_case() -> ListRunsUseCase:
    raise NotImplementedError("ListRunsUseCase not initialized")


def get_list_my_runs_use_case() -> ListMyRunsUseCase:
    raise NotImplementedError("ListMyRunsUseCase not initialized")


def get_usage_summary_use_case() -> GetUsageSummaryUseCase:
    raise NotImplementedError("GetUsageSummaryUseCase not initialized")


def get_usage_timeseries_use_case() -> GetUsageTimeseriesUseCase:
    raise NotImplementedError("GetUsageTimeseriesUseCase not initialized")


def get_my_usage_timeseries_use_case() -> GetMyUsageTimeseriesUseCase:
    raise NotImplementedError("GetMyUsageTimeseriesUseCase not initialized")


# -------- Helpers --------


def _resolve_period(
    from_: Optional[datetime], to: Optional[datetime]
) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    to_dt = to or now
    from_dt = from_ or (to_dt - timedelta(days=30))
    if from_dt > to_dt:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="from must be <= to",
        )
    if (to_dt - from_dt).days > 366:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="period must be <= 366 days",
        )
    return from_dt, to_dt


# -------- Endpoints --------


@router.get("/agents/runs/{run_id}", response_model=RunDetailResponse)
async def get_run_detail(
    run_id: str,
    current_user: User = Depends(get_current_user),
    use_case: GetRunDetailUseCase = Depends(get_run_detail_use_case),
) -> RunDetailResponse:
    """Run 상세 트리: run + steps + (tool_calls/retrievals/llm_calls)."""
    is_admin = current_user.role == UserRole.ADMIN
    try:
        dto = await use_case.execute(
            run_id=run_id,
            requesting_user_id=str(current_user.id),
            is_admin=is_admin,
        )
    except RunNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )
    except RunAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    return RunDetailResponse.from_dto(dto)


@router.get("/admin/usage/users", response_model=UsageByUserResponse)
async def get_admin_usage_by_user(
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    _: User = Depends(require_role("admin")),
    use_case: GetUsageByUserUseCase = Depends(get_usage_by_user_use_case),
) -> UsageByUserResponse:
    from_dt, to_dt = _resolve_period(from_, to)
    rows = await use_case.execute(from_dt, to_dt)
    return UsageByUserResponse.from_rows(rows, from_dt=from_dt, to_dt=to_dt)


@router.get("/admin/usage/llm-models", response_model=UsageByLlmResponse)
async def get_admin_usage_by_llm(
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    _: User = Depends(require_role("admin")),
    use_case: GetUsageByLlmUseCase = Depends(get_usage_by_llm_use_case),
) -> UsageByLlmResponse:
    from_dt, to_dt = _resolve_period(from_, to)
    rows = await use_case.execute(from_dt, to_dt)
    return UsageByLlmResponse.from_rows(rows, from_dt=from_dt, to_dt=to_dt)


@router.get("/admin/usage/by-node", response_model=UsageByNodeResponse)
async def get_admin_usage_by_node(
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    _: User = Depends(require_role("admin")),
    use_case: GetUsageByNodeUseCase = Depends(get_usage_by_node_use_case),
) -> UsageByNodeResponse:
    """노드별 토큰/비용 GROUP BY (★ M3 step_id JOIN 효과)."""
    from_dt, to_dt = _resolve_period(from_, to)
    rows = await use_case.execute(from_dt, to_dt)
    return UsageByNodeResponse.from_rows(rows, from_dt=from_dt, to_dt=to_dt)


@router.get("/usage/me", response_model=UsageByLlmResponse)
async def get_usage_me(
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_user),
    use_case: GetUsageMeUseCase = Depends(get_usage_me_use_case),
) -> UsageByLlmResponse:
    """현재 사용자 본인의 LLM 모델별 사용량."""
    from_dt, to_dt = _resolve_period(from_, to)
    rows = await use_case.execute(str(current_user.id), from_dt, to_dt)
    return UsageByLlmResponse.from_rows(rows, from_dt=from_dt, to_dt=to_dt)


@router.get("/admin/runs", response_model=RunListResponse)
async def get_admin_runs(
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    user_id: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    status_: Optional[str] = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _: User = Depends(require_role("admin")),
    use_case: ListRunsUseCase = Depends(get_list_runs_use_case),
) -> RunListResponse:
    """관리자 Run 목록 (페이지네이션 + 필터, ★ M5).

    필터: from/to (period), user_id, agent_id, status (RUNNING/SUCCESS/FAILED/CANCELLED).
    페이지네이션: limit (1-100, default 20) + offset (>=0, default 0).
    """
    # period 검증 (M4의 _resolve_period는 default 30일 강제 — list_runs는 default None 허용)
    if from_ is not None and to is not None and from_ > to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="from must be <= to",
        )

    filters = RunListFilters(
        from_dt=from_,
        to_dt=to,
        user_id=user_id,
        agent_id=agent_id,
        status=status_,
        limit=limit,
        offset=offset,
    )
    try:
        dto = await use_case.execute(filters)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    return RunListResponse.from_dto(dto)


# ── M5: Dashboard summary + timeseries (admin) ────────────────────


@router.get("/admin/usage/summary", response_model=UsageSummaryResponse)
async def get_admin_usage_summary(
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    _: User = Depends(require_role("admin")),
    use_case: GetUsageSummaryUseCase = Depends(get_usage_summary_use_case),
) -> UsageSummaryResponse:
    """대시보드 카드 4종 (총 Run·성공률·총 토큰·총 비용). ★ M5."""
    from_dt, to_dt = _resolve_period(from_, to)
    row = await use_case.execute(from_dt, to_dt, user_id=None)
    return UsageSummaryResponse.from_row(row)


@router.get("/admin/usage/timeseries", response_model=UsageTimeseriesResponse)
async def get_admin_usage_timeseries(
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    _: User = Depends(require_role("admin")),
    use_case: GetUsageTimeseriesUseCase = Depends(get_usage_timeseries_use_case),
) -> UsageTimeseriesResponse:
    """일자별 비용·토큰·run 수 시계열 (bucket=day). ★ M5."""
    from_dt, to_dt = _resolve_period(from_, to)
    points = await use_case.execute(from_dt, to_dt, user_id=None)
    return UsageTimeseriesResponse.from_points(points, from_dt=from_dt, to_dt=to_dt)


# ── M5: My Usage (사용자 본인) ────────────────────────────────────


@router.get("/usage/me/runs", response_model=RunListResponse)
async def get_my_runs(
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    agent_id: Optional[str] = Query(None),
    status_: Optional[str] = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    use_case: ListMyRunsUseCase = Depends(get_list_my_runs_use_case),
) -> RunListResponse:
    """본인 Run 목록 (★ M5). user_id 쿼리 파라미터는 미수용 — current_user.id 강제."""
    if from_ is not None and to is not None and from_ > to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="from must be <= to",
        )
    filters = RunListFilters(
        from_dt=from_,
        to_dt=to,
        agent_id=agent_id,
        status=status_,
        limit=limit,
        offset=offset,
    )
    try:
        dto = await use_case.execute(
            user_id=str(current_user.id), filters=filters
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    return RunListResponse.from_dto(dto)


@router.get("/usage/me/timeseries", response_model=UsageTimeseriesResponse)
async def get_my_usage_timeseries(
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_user),
    use_case: GetMyUsageTimeseriesUseCase = Depends(get_my_usage_timeseries_use_case),
) -> UsageTimeseriesResponse:
    """본인 일자별 시계열 (★ M5). user_id 는 current_user.id 강제."""
    from_dt, to_dt = _resolve_period(from_, to)
    points = await use_case.execute(str(current_user.id), from_dt, to_dt)
    return UsageTimeseriesResponse.from_points(points, from_dt=from_dt, to_dt=to_dt)
