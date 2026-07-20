"""admin-dashboard 도메인 DTO (Design §3.2).

읽기 전용 집계 결과 — 비즈니스 규칙 없음.
"""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class KbStats:
    total: int
    active: int
    by_scope: dict[str, int]


@dataclass(frozen=True)
class DocumentStats:
    total: int
    with_kb: int
    without_kb: int


@dataclass(frozen=True)
class ChunkStats:
    total: int


@dataclass(frozen=True)
class UserStats:
    total: int
    approved: int
    pending: int
    admins: int


@dataclass(frozen=True)
class DashboardStats:
    kb: KbStats
    documents: DocumentStats
    chunks: ChunkStats
    users: UserStats


@dataclass(frozen=True)
class KbBreakdownRow:
    kb_id: str
    name: str
    scope: str
    status: str
    document_count: int
    chunk_count: int
    last_uploaded_at: datetime | None


@dataclass(frozen=True)
class RecentDocumentRow:
    document_id: str
    filename: str
    kb_id: str | None
    kb_name: str | None
    collection_name: str
    chunk_count: int
    chunk_strategy: str
    created_at: datetime


@dataclass(frozen=True)
class HealthComponent:
    name: str
    status: str  # "ok" | "fail"
    latency_ms: int | None
    error: str | None
