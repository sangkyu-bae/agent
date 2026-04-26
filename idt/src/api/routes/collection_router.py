"""Collection Management Router: Qdrant 컬렉션 CRUD + 사용이력 조회 API."""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.application.collection.activity_log_service import ActivityLogService
from src.application.collection.use_case import CollectionManagementUseCase
from src.domain.auth.entities import User
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.collection.schemas import DistanceMetric
from src.interfaces.dependencies.auth import get_current_user

router = APIRouter(prefix="/api/v1/collections", tags=["Collections"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_collection_use_case() -> CollectionManagementUseCase:
    raise NotImplementedError


def get_activity_log_service() -> ActivityLogService:
    raise NotImplementedError


# ── Request / Response Schemas ───────────────────────────────────

class CreateCollectionBody(BaseModel):
    name: str
    vector_size: int | None = Field(default=None, ge=1)
    embedding_model: str | None = None
    distance: str = "Cosine"
    scope: str = "PERSONAL"
    department_id: str | None = None


class RenameCollectionBody(BaseModel):
    new_name: str


class ChangeScopeBody(BaseModel):
    scope: str
    department_id: str | None = None


class CollectionInfoResponse(BaseModel):
    name: str
    vectors_count: int
    points_count: int
    status: str
    scope: str | None = None
    owner_id: int | None = None


class CollectionConfigResponse(BaseModel):
    vector_size: int
    distance: str


class CollectionDetailResponse(BaseModel):
    name: str
    vectors_count: int
    points_count: int
    status: str
    config: CollectionConfigResponse


class CollectionListResponse(BaseModel):
    collections: list[CollectionInfoResponse]
    total: int


class ActivityLogResponse(BaseModel):
    id: int
    collection_name: str
    action: str
    user_id: str | None
    detail: dict | None
    created_at: datetime


class ActivityLogListResponse(BaseModel):
    logs: list[ActivityLogResponse]
    total: int
    limit: int
    offset: int


class MessageResponse(BaseModel):
    name: str
    message: str


class RenameResponse(BaseModel):
    old_name: str
    new_name: str
    message: str


# ── Endpoints (라우팅 순서 중요: /activity-log 이 /{name} 위에) ──


@router.get("", response_model=CollectionListResponse)
async def list_collections(
    current_user: User = Depends(get_current_user),
    use_case: CollectionManagementUseCase = Depends(get_collection_use_case),
):
    request_id = str(uuid.uuid4())
    result = await use_case.list_collections(
        request_id,
        user_id=str(current_user.id),
        user=current_user,
    )
    perm_map = await use_case.get_permissions_map(
        [c.name for c in result], request_id
    )
    return CollectionListResponse(
        collections=[
            CollectionInfoResponse(
                name=c.name,
                vectors_count=c.vectors_count,
                points_count=c.points_count,
                status=c.status,
                scope=perm_map[c.name][0] if c.name in perm_map else None,
                owner_id=perm_map[c.name][1] if c.name in perm_map else None,
            )
            for c in result
        ],
        total=len(result),
    )


@router.get("/activity-log", response_model=ActivityLogListResponse)
async def get_activity_logs(
    collection_name: str | None = Query(None),
    action: str | None = Query(None),
    user_id: str | None = Query(None),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    activity_log: ActivityLogService = Depends(get_activity_log_service),
):
    request_id = str(uuid.uuid4())
    logs, total = await activity_log.get_logs(
        request_id=request_id,
        collection_name=collection_name,
        action=action,
        user_id=user_id,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )
    return ActivityLogListResponse(
        logs=[
            ActivityLogResponse(
                id=entry.id,
                collection_name=entry.collection_name,
                action=entry.action.value,
                user_id=entry.user_id,
                detail=entry.detail,
                created_at=entry.created_at,
            )
            for entry in logs
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{name}", response_model=CollectionDetailResponse)
async def get_collection(
    name: str,
    current_user: User = Depends(get_current_user),
    use_case: CollectionManagementUseCase = Depends(get_collection_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        result = await use_case.get_collection(
            name, request_id,
            user_id=str(current_user.id),
            user=current_user,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return CollectionDetailResponse(
        name=result.name,
        vectors_count=result.vectors_count,
        points_count=result.points_count,
        status=result.status,
        config=CollectionConfigResponse(
            vector_size=result.vector_size,
            distance=result.distance,
        ),
    )


@router.get("/{name}/activity-log", response_model=ActivityLogListResponse)
async def get_collection_activity_logs(
    name: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    activity_log: ActivityLogService = Depends(get_activity_log_service),
):
    request_id = str(uuid.uuid4())
    logs, total = await activity_log.get_collection_logs(
        collection_name=name,
        request_id=request_id,
        limit=limit,
        offset=offset,
    )
    return ActivityLogListResponse(
        logs=[
            ActivityLogResponse(
                id=entry.id,
                collection_name=entry.collection_name,
                action=entry.action.value,
                user_id=entry.user_id,
                detail=entry.detail,
                created_at=entry.created_at,
            )
            for entry in logs
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", status_code=201, response_model=MessageResponse)
async def create_collection(
    body: CreateCollectionBody,
    current_user: User = Depends(get_current_user),
    use_case: CollectionManagementUseCase = Depends(get_collection_use_case),
):
    request_id = str(uuid.uuid4())
    from src.domain.collection.schemas import CreateCollectionRequest

    if body.vector_size is None and body.embedding_model is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Either 'vector_size' or 'embedding_model' is required",
        )

    try:
        distance = DistanceMetric(body.distance)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid distance metric: '{body.distance}'",
        )

    try:
        scope = CollectionScope(body.scope)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid scope: '{body.scope}'",
        )

    req = CreateCollectionRequest(
        name=body.name,
        vector_size=body.vector_size or 0,
        distance=distance,
        embedding_model=body.embedding_model,
    )
    try:
        await use_case.create_collection(
            req, request_id,
            user_id=str(current_user.id),
            user=current_user,
            scope=scope,
            department_id=body.department_id,
        )
    except ValueError as e:
        msg = str(e)
        if "already exists" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg
        )
    return MessageResponse(name=body.name, message="Collection created successfully")


@router.patch("/{name}", response_model=RenameResponse)
async def rename_collection(
    name: str,
    body: RenameCollectionBody,
    current_user: User = Depends(get_current_user),
    use_case: CollectionManagementUseCase = Depends(get_collection_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        await use_case.rename_collection(
            name, body.new_name, request_id,
            user_id=str(current_user.id),
            user=current_user,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg
        )
    return RenameResponse(
        old_name=name,
        new_name=body.new_name,
        message="Collection alias updated successfully",
    )


@router.delete("/{name}", response_model=MessageResponse)
async def delete_collection(
    name: str,
    current_user: User = Depends(get_current_user),
    use_case: CollectionManagementUseCase = Depends(get_collection_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        await use_case.delete_collection(
            name, request_id,
            user_id=str(current_user.id),
            user=current_user,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        msg = str(e)
        if "Cannot delete protected" in msg:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=msg)
        if "not found" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg
        )
    return MessageResponse(name=name, message="Collection deleted successfully")


@router.patch("/{name}/permission", response_model=MessageResponse)
async def change_collection_scope(
    name: str,
    body: ChangeScopeBody,
    current_user: User = Depends(get_current_user),
    use_case: CollectionManagementUseCase = Depends(get_collection_use_case),
):
    request_id = str(uuid.uuid4())
    try:
        scope = CollectionScope(body.scope)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid scope: '{body.scope}'",
        )
    try:
        await use_case.change_scope(
            name, current_user, scope, body.department_id, request_id,
        )
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Permission service not configured",
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        msg = str(e)
        if "not found" in msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg
        )
    return MessageResponse(name=name, message="Collection scope updated successfully")
