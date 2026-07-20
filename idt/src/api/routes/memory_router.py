"""Memory Router: 사용자 메모리 CRUD API (agent-memory Design §3-4).

전 엔드포인트 get_current_user 필수 — 메모리 키는 str(user.id)
(agent_builder_router 선례와 동일 변환).
에러 계약(결정 ②): 401 미인증 / 404 타인·미존재 은닉 / 422 검증.
DI는 main.py에서 dependency_overrides로 주입한다.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException

from src.application.memory.api_schemas import (
    CreateMemoryRequest,
    MemoryListResponse,
    MemoryResponse,
    UpdateMemoryRequest,
    to_response,
)
from src.domain.auth.entities import User
from src.domain.memory.entity import MemoryStatus
from src.interfaces.dependencies.auth import get_current_user

router = APIRouter(prefix="/api/v1/memories", tags=["Memory"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_memory_crud_use_case():
    raise NotImplementedError


def _raise_memory_error(exc: ValueError) -> None:
    """타인·미존재("찾을 수 없")는 404로 은닉, 그 외 검증 실패는 422."""
    msg = str(exc)
    raise HTTPException(status_code=404 if "찾을 수 없" in msg else 422, detail=msg)


# ── 엔드포인트 ────────────────────────────────────────────────────


@router.get("", response_model=MemoryListResponse)
async def list_memories(
    status: str = "active",
    use_case=Depends(get_memory_crud_use_case),
    user: User = Depends(get_current_user),
):
    """본인 메모리 목록 — 기본 active, status=pending은 승인 대기 (Phase 2).

    max_count는 조회 status의 상한(active=30, pending=20)으로 프론트 안내.
    """
    request_id = str(uuid.uuid4())
    if status == "active":
        items = await use_case.list_active(str(user.id), request_id)
        max_count = use_case.max_active_per_user
    elif status == "pending":
        items = await use_case.list_by_status(
            str(user.id), MemoryStatus.PENDING, request_id
        )
        max_count = use_case.max_pending_per_user
    else:
        raise HTTPException(status_code=422, detail=f"Invalid status: {status}")
    return MemoryListResponse(
        items=[to_response(m) for m in items],
        total=len(items),
        max_count=max_count,
    )


@router.post("", response_model=MemoryResponse, status_code=201)
async def create_memory(
    body: CreateMemoryRequest,
    use_case=Depends(get_memory_crud_use_case),
    user: User = Depends(get_current_user),
):
    """메모리 등록 — Phase 1은 즉시 active."""
    request_id = str(uuid.uuid4())
    try:
        memory = await use_case.create(
            str(user.id), body.mem_type, body.content, request_id
        )
    except ValueError as e:
        _raise_memory_error(e)
    return to_response(memory)


@router.patch("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: int,
    body: UpdateMemoryRequest,
    use_case=Depends(get_memory_crud_use_case),
    user: User = Depends(get_current_user),
):
    """본인 메모리 부분 수정 (mem_type/content)."""
    request_id = str(uuid.uuid4())
    try:
        memory = await use_case.update(
            str(user.id), memory_id, body.mem_type, body.content, request_id
        )
    except ValueError as e:
        _raise_memory_error(e)
    return to_response(memory)


@router.patch("/{memory_id}/approve", response_model=MemoryResponse)
async def approve_memory(
    memory_id: int,
    use_case=Depends(get_memory_crud_use_case),
    user: User = Depends(get_current_user),
):
    """추출 후보 승인 (pending→active) — 승인 후 주입 대상이 된다."""
    request_id = str(uuid.uuid4())
    try:
        memory = await use_case.approve(str(user.id), memory_id, request_id)
    except ValueError as e:
        _raise_memory_error(e)
    return to_response(memory)


@router.patch("/{memory_id}/reject", response_model=MemoryResponse)
async def reject_memory(
    memory_id: int,
    use_case=Depends(get_memory_crud_use_case),
    user: User = Depends(get_current_user),
):
    """추출 후보 거부 (pending→rejected) — 재노출되지 않는다."""
    request_id = str(uuid.uuid4())
    try:
        memory = await use_case.reject(str(user.id), memory_id, request_id)
    except ValueError as e:
        _raise_memory_error(e)
    return to_response(memory)


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: int,
    use_case=Depends(get_memory_crud_use_case),
    user: User = Depends(get_current_user),
):
    """본인 메모리 삭제."""
    request_id = str(uuid.uuid4())
    try:
        await use_case.delete(str(user.id), memory_id, request_id)
    except ValueError as e:
        _raise_memory_error(e)
