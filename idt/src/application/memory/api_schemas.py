"""Memory API 요청/응답 스키마 (agent-memory Design §3-4).

Phase 1 응답은 사용자 노출 필드만 포함 — scope/tier/status/confidence 등
내부 필드는 제외한다(수동 active만 존재).
"""
from datetime import datetime

from pydantic import BaseModel

from src.domain.memory.entity import Memory


class CreateMemoryRequest(BaseModel):
    mem_type: str
    content: str


class CreateOrgMemoryRequest(BaseModel):
    dept_id: str
    mem_type: str
    content: str


class PromoteMemoryRequest(BaseModel):
    dept_id: str


class UpdateMemoryRequest(BaseModel):
    mem_type: str | None = None
    content: str | None = None


class MemoryResponse(BaseModel):
    id: int
    mem_type: str
    content: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MemoryListResponse(BaseModel):
    items: list[MemoryResponse]
    total: int
    max_count: int


def to_response(memory: Memory) -> MemoryResponse:
    return MemoryResponse(
        id=memory.id,
        mem_type=memory.mem_type.value,
        content=memory.content,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
    )
