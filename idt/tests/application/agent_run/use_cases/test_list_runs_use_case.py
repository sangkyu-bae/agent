"""M5-5: ListRunsUseCase 단위 테스트.

agent-run-observability-m5 Design §3.3, §9.1.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_run.use_cases.list_runs_use_case import (
    ListRunsUseCase,
    RunListDto,
)
from src.domain.agent_run.interfaces import RunListFilters


def _make_use_case(rows: list = None, total: int = 0):
    repo = MagicMock()
    repo.list_runs = AsyncMock(return_value=rows or [])
    repo.count_runs = AsyncMock(return_value=total)
    logger = MagicMock()
    uc = ListRunsUseCase(agent_run_repo=repo, logger=logger)
    return uc, repo


class TestExecute:
    @pytest.mark.asyncio
    async def test_executes_list_and_count_concurrently(self):
        """list_runs + count_runs 동시 호출 (asyncio.gather) — 같은 필터."""
        uc, repo = _make_use_case(rows=[], total=42)
        filters = RunListFilters(
            from_dt=datetime(2026, 5, 1, tzinfo=timezone.utc),
            to_dt=datetime(2026, 5, 31, tzinfo=timezone.utc),
            user_id="user-1",
            limit=10,
            offset=0,
        )

        dto = await uc.execute(filters)

        assert isinstance(dto, RunListDto)
        assert dto.total == 42
        assert dto.limit == 10
        assert dto.offset == 0
        # 두 호출 모두 같은 filters
        repo.list_runs.assert_awaited_once_with(filters)
        repo.count_runs.assert_awaited_once_with(filters)


class TestValidation:
    @pytest.mark.asyncio
    async def test_rejects_limit_over_max(self):
        uc, _ = _make_use_case()
        filters = RunListFilters(limit=101)
        with pytest.raises(ValueError, match="limit"):
            await uc.execute(filters)

    @pytest.mark.asyncio
    async def test_rejects_invalid_status(self):
        uc, _ = _make_use_case()
        filters = RunListFilters(status="INVALID_STATUS")
        with pytest.raises(ValueError, match="status"):
            await uc.execute(filters)

    @pytest.mark.asyncio
    async def test_rejects_from_after_to(self):
        uc, _ = _make_use_case()
        filters = RunListFilters(
            from_dt=datetime(2026, 6, 1, tzinfo=timezone.utc),
            to_dt=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        with pytest.raises(ValueError, match="from"):
            await uc.execute(filters)

    @pytest.mark.asyncio
    async def test_accepts_valid_status_values(self):
        """RunStatus enum 4값 모두 허용 — RUNNING/SUCCESS/FAILED/CANCELLED."""
        for status in ("RUNNING", "SUCCESS", "FAILED", "CANCELLED"):
            uc, _ = _make_use_case()
            filters = RunListFilters(status=status)
            dto = await uc.execute(filters)
            assert dto is not None
