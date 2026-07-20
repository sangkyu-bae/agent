"""admin-dashboard 포트 정의 (Design D3)."""
from abc import ABC, abstractmethod

from src.domain.admin_dashboard.schemas import (
    DashboardStats,
    HealthComponent,
    KbBreakdownRow,
    RecentDocumentRow,
)


class DashboardAggregationRepositoryInterface(ABC):
    """MySQL 메타 기준 읽기 전용 집계 포트."""

    @abstractmethod
    async def get_stats(self) -> DashboardStats:
        """KB/문서/청크/사용자 누적 현황."""

    @abstractmethod
    async def get_kb_breakdown(self) -> list[KbBreakdownRow]:
        """KB별 문서/청크 집계 — 문서 0건 KB 포함."""

    @abstractmethod
    async def get_recent_documents(self, limit: int) -> list[RecentDocumentRow]:
        """최근 적재 문서 (created_at DESC)."""


class StorageHealthPort(ABC):
    """저장소(MySQL/Qdrant/ES) 헬스체크 포트 — 부분 실패 격리."""

    @abstractmethod
    async def check_all(self) -> list[HealthComponent]:
        """모든 컴포넌트를 병렬 ping — 실패는 컴포넌트 단위 fail로 반환."""
