"""Admin Collection Router: 관리자 전용 물리 컬렉션 생성 (knowledge-base-scoping Design §7.2).

기존 POST /api/v1/collections는 무수정 유지. 신규 경로는 require_role('admin') 가드 후
기존 collection_router.create_collection 핸들러에 위임한다 (로직 복제 금지).
"""
from fastapi import APIRouter, Depends

from src.api.routes.collection_router import (
    CreateCollectionBody,
    MessageResponse,
    create_collection,
    get_collection_use_case,
)
from src.application.collection.use_case import CollectionManagementUseCase
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import require_role

router = APIRouter(prefix="/api/v1/admin/collections", tags=["Admin"])


class AdminCreateCollectionBody(CreateCollectionBody):
    # 관리자 컬렉션은 공용 전제 — 기본 스코프 PUBLIC (Design §7.2)
    scope: str = "PUBLIC"


@router.post("", status_code=201, response_model=MessageResponse)
async def create_collection_admin(
    body: AdminCreateCollectionBody,
    current_user: User = Depends(require_role("admin")),
    use_case: CollectionManagementUseCase = Depends(get_collection_use_case),
):
    return await create_collection(body, current_user, use_case)
