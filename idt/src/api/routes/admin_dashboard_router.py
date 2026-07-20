"""Admin dashboard router: /api/v1/admin/dashboard/* (admin 전용, Design D2).

읽기 전용 — 기간 지표는 기존 /admin/usage/* 재사용 (D1), 여기는 누적 현황·헬스만.
"""
import uuid

from fastapi import APIRouter, Depends, Query

from src.application.admin_dashboard.use_cases import (
    GetDashboardStatsUseCase,
    GetKbBreakdownUseCase,
    GetRecentDocumentsUseCase,
    StorageHealthCheckUseCase,
)
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import require_role
from src.interfaces.schemas.admin_dashboard_response import (
    DashboardStatsResponse,
    KbBreakdownResponse,
    RecentDocumentsResponse,
    StorageHealthResponse,
)

router = APIRouter(prefix="/api/v1/admin/dashboard", tags=["admin-dashboard"])


# -------- DI placeholders (override in create_app) --------


def get_dashboard_stats_use_case() -> GetDashboardStatsUseCase:
    raise NotImplementedError("GetDashboardStatsUseCase not initialized")


def get_kb_breakdown_use_case() -> GetKbBreakdownUseCase:
    raise NotImplementedError("GetKbBreakdownUseCase not initialized")


def get_recent_documents_use_case() -> GetRecentDocumentsUseCase:
    raise NotImplementedError("GetRecentDocumentsUseCase not initialized")


def get_storage_health_use_case() -> StorageHealthCheckUseCase:
    raise NotImplementedError("StorageHealthCheckUseCase not initialized")


# -------- Endpoints --------


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_stats(
    _: User = Depends(require_role("admin")),
    use_case: GetDashboardStatsUseCase = Depends(get_dashboard_stats_use_case),
) -> DashboardStatsResponse:
    """KB/문서/청크/사용자 누적 현황 — MySQL 메타 기준 (기간 무관, D1)."""
    dto = await use_case.execute(request_id=str(uuid.uuid4()))
    return DashboardStatsResponse.from_dto(dto)


@router.get("/kb-breakdown", response_model=KbBreakdownResponse)
async def get_kb_breakdown(
    _: User = Depends(require_role("admin")),
    use_case: GetKbBreakdownUseCase = Depends(get_kb_breakdown_use_case),
) -> KbBreakdownResponse:
    """KB별 문서/청크 현황 — 문서 0건 KB 포함 (D4)."""
    rows = await use_case.execute(request_id=str(uuid.uuid4()))
    return KbBreakdownResponse.from_rows(rows)


@router.get("/recent-documents", response_model=RecentDocumentsResponse)
async def get_recent_documents(
    limit: int = Query(10, ge=1, le=50),
    _: User = Depends(require_role("admin")),
    use_case: GetRecentDocumentsUseCase = Depends(get_recent_documents_use_case),
) -> RecentDocumentsResponse:
    """최근 적재 문서 목록 (created_at DESC, D9)."""
    rows = await use_case.execute(limit=limit, request_id=str(uuid.uuid4()))
    return RecentDocumentsResponse.from_rows(rows)


@router.get("/health", response_model=StorageHealthResponse)
async def get_storage_health(
    _: User = Depends(require_role("admin")),
    use_case: StorageHealthCheckUseCase = Depends(get_storage_health_use_case),
) -> StorageHealthResponse:
    """MySQL/Qdrant/ES 헬스 — 부분 실패도 HTTP 200 (D5)."""
    components = await use_case.execute(request_id=str(uuid.uuid4()))
    return StorageHealthResponse.from_components(components)
