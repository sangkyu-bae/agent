"""Middleware Catalog Router: 미들웨어 카탈로그 조회 + 관리자 토글 (builtin-middleware D4)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException

from src.application.middleware.schemas import (
    MiddlewareCatalogItemResponse,
    MiddlewareCatalogListResponse,
    SetMiddlewareFlagsRequest,
)
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user, require_role

router = APIRouter(prefix="/api/v1/middleware-catalog", tags=["Middleware Catalog"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_list_middleware_catalog_use_case():
    raise NotImplementedError


def get_set_middleware_flags_use_case():
    raise NotImplementedError


# ── 엔드포인트 ────────────────────────────────────────────────────


@router.get("", response_model=MiddlewareCatalogListResponse)
async def list_middleware_catalog(
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_list_middleware_catalog_use_case),
):
    """카탈로그 목록 — 생성/수정 폼(빌트인·enforced 표시)과 관리자 화면 공용."""
    request_id = str(uuid.uuid4())
    return await use_case.execute(request_id)


@router.patch("/{middleware_type}", response_model=MiddlewareCatalogItemResponse)
async def set_middleware_flags(
    middleware_type: str,
    body: SetMiddlewareFlagsRequest,
    current_user: User = Depends(require_role("admin")),
    use_case=Depends(get_set_middleware_flags_use_case),
):
    """빌트인/강제/기본 설정 부분 갱신 (관리자 전용).

    middleware_type은 enum 값(콜론 없음)이라 path 파라미터 적합 —
    tool_catalog가 body로 받은 이유(mcp:{uuid}:{tool})가 여기엔 없다.
    """
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            middleware_type,
            is_builtin=body.is_builtin,
            is_enforced=body.is_enforced,
            default_config=body.default_config,
            request_id=request_id,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
