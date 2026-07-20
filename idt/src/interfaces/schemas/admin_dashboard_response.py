"""admin-dashboard 응답 스키마 (Design §3.2)."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from src.domain.admin_dashboard.schemas import (
    DashboardStats,
    HealthComponent,
    KbBreakdownRow,
    RecentDocumentRow,
)


class KbStatsResponse(BaseModel):
    total: int
    active: int
    by_scope: dict[str, int]


class DocumentStatsResponse(BaseModel):
    total: int
    with_kb: int
    without_kb: int


class ChunkStatsResponse(BaseModel):
    total: int


class UserStatsResponse(BaseModel):
    total: int
    approved: int
    pending: int
    admins: int


class DashboardStatsResponse(BaseModel):
    kb: KbStatsResponse
    documents: DocumentStatsResponse
    chunks: ChunkStatsResponse
    users: UserStatsResponse

    @classmethod
    def from_dto(cls, dto: DashboardStats) -> "DashboardStatsResponse":
        return cls(
            kb=KbStatsResponse(
                total=dto.kb.total, active=dto.kb.active, by_scope=dto.kb.by_scope
            ),
            documents=DocumentStatsResponse(
                total=dto.documents.total,
                with_kb=dto.documents.with_kb,
                without_kb=dto.documents.without_kb,
            ),
            chunks=ChunkStatsResponse(total=dto.chunks.total),
            users=UserStatsResponse(
                total=dto.users.total,
                approved=dto.users.approved,
                pending=dto.users.pending,
                admins=dto.users.admins,
            ),
        )


class KbBreakdownRowResponse(BaseModel):
    kb_id: str
    name: str
    scope: str
    status: str
    document_count: int
    chunk_count: int
    last_uploaded_at: Optional[datetime]


class KbBreakdownResponse(BaseModel):
    rows: List[KbBreakdownRowResponse]

    @classmethod
    def from_rows(cls, rows: list[KbBreakdownRow]) -> "KbBreakdownResponse":
        return cls(
            rows=[
                KbBreakdownRowResponse(
                    kb_id=r.kb_id,
                    name=r.name,
                    scope=r.scope,
                    status=r.status,
                    document_count=r.document_count,
                    chunk_count=r.chunk_count,
                    last_uploaded_at=r.last_uploaded_at,
                )
                for r in rows
            ]
        )


class RecentDocumentRowResponse(BaseModel):
    document_id: str
    filename: str
    kb_id: Optional[str]
    kb_name: Optional[str]
    collection_name: str
    chunk_count: int
    chunk_strategy: str
    created_at: datetime


class RecentDocumentsResponse(BaseModel):
    rows: List[RecentDocumentRowResponse]

    @classmethod
    def from_rows(cls, rows: list[RecentDocumentRow]) -> "RecentDocumentsResponse":
        return cls(
            rows=[
                RecentDocumentRowResponse(
                    document_id=r.document_id,
                    filename=r.filename,
                    kb_id=r.kb_id,
                    kb_name=r.kb_name,
                    collection_name=r.collection_name,
                    chunk_count=r.chunk_count,
                    chunk_strategy=r.chunk_strategy,
                    created_at=r.created_at,
                )
                for r in rows
            ]
        )


class HealthComponentResponse(BaseModel):
    name: str
    status: str
    latency_ms: Optional[int]
    error: Optional[str]


class StorageHealthResponse(BaseModel):
    components: List[HealthComponentResponse]

    @classmethod
    def from_components(
        cls, components: list[HealthComponent]
    ) -> "StorageHealthResponse":
        return cls(
            components=[
                HealthComponentResponse(
                    name=c.name,
                    status=c.status,
                    latency_ms=c.latency_ms,
                    error=c.error,
                )
                for c in components
            ]
        )
