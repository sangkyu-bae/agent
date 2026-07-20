"""admin-dashboard 유스케이스 단위 테스트 (Design §5.1)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.admin_dashboard.use_cases import (
    GetDashboardStatsUseCase,
    GetKbBreakdownUseCase,
    GetRecentDocumentsUseCase,
    StorageHealthCheckUseCase,
)
from src.domain.admin_dashboard.schemas import (
    ChunkStats,
    DashboardStats,
    DocumentStats,
    HealthComponent,
    KbBreakdownRow,
    KbStats,
    RecentDocumentRow,
    UserStats,
)


def _make_stats() -> DashboardStats:
    return DashboardStats(
        kb=KbStats(total=3, active=2, by_scope={"PERSONAL": 1, "PUBLIC": 2}),
        documents=DocumentStats(total=10, with_kb=8, without_kb=2),
        chunks=ChunkStats(total=120),
        users=UserStats(total=5, approved=4, pending=1, admins=1),
    )


class TestGetDashboardStatsUseCase:
    @pytest.mark.asyncio
    async def test_returns_stats_from_repo(self):
        repo = AsyncMock()
        repo.get_stats.return_value = _make_stats()
        uc = GetDashboardStatsUseCase(repo=repo, logger=MagicMock())

        result = await uc.execute(request_id="req-1")

        assert result.kb.total == 3
        assert result.documents.without_kb == 2
        assert result.chunks.total == 120
        assert result.users.approved == 4
        repo.get_stats.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_logs_and_reraises_on_error(self):
        repo = AsyncMock()
        repo.get_stats.side_effect = RuntimeError("db down")
        logger = MagicMock()
        uc = GetDashboardStatsUseCase(repo=repo, logger=logger)

        with pytest.raises(RuntimeError, match="db down"):
            await uc.execute(request_id="req-1")
        logger.error.assert_called_once()


class TestGetKbBreakdownUseCase:
    @pytest.mark.asyncio
    async def test_returns_rows_including_empty_kb(self):
        repo = AsyncMock()
        repo.get_kb_breakdown.return_value = [
            KbBreakdownRow(
                kb_id="kb-1", name="규정집", scope="PUBLIC", status="active",
                document_count=5, chunk_count=100,
                last_uploaded_at=datetime(2026, 7, 17, 9, 0),
            ),
            KbBreakdownRow(
                kb_id="kb-2", name="빈 KB", scope="PERSONAL", status="active",
                document_count=0, chunk_count=0, last_uploaded_at=None,
            ),
        ]
        uc = GetKbBreakdownUseCase(repo=repo, logger=MagicMock())

        rows = await uc.execute(request_id="req-1")

        assert len(rows) == 2
        assert rows[1].document_count == 0
        assert rows[1].last_uploaded_at is None


class TestGetRecentDocumentsUseCase:
    @pytest.mark.asyncio
    async def test_passes_limit_to_repo(self):
        repo = AsyncMock()
        repo.get_recent_documents.return_value = [
            RecentDocumentRow(
                document_id="d1", filename="a.pdf", kb_id=None, kb_name=None,
                collection_name="col", chunk_count=3, chunk_strategy="parent_child",
                created_at=datetime(2026, 7, 18, 8, 0),
            ),
        ]
        uc = GetRecentDocumentsUseCase(repo=repo, logger=MagicMock())

        rows = await uc.execute(limit=5, request_id="req-1")

        repo.get_recent_documents.assert_awaited_once_with(limit=5)
        assert rows[0].kb_name is None


class TestStorageHealthCheckUseCase:
    @pytest.mark.asyncio
    async def test_returns_components_even_with_failures(self):
        port = AsyncMock()
        port.check_all.return_value = [
            HealthComponent(name="mysql", status="ok", latency_ms=4, error=None),
            HealthComponent(
                name="elasticsearch", status="fail", latency_ms=None,
                error="timeout(3s)",
            ),
        ]
        uc = StorageHealthCheckUseCase(port=port, logger=MagicMock())

        components = await uc.execute(request_id="req-1")

        assert len(components) == 2
        assert components[1].status == "fail"
