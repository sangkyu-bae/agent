"""ListMyScheduleRunsUseCase 단위 테스트 (background-jobs §7-7, D9)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.background_job.list_my_schedule_runs_use_case import (
    ListMyScheduleRunsUseCase,
)
from src.domain.agent_schedule.entity import ScheduleRun

_NOW = datetime(2026, 8, 11, 3, 0)


def _run(run_id="r1", status="success") -> ScheduleRun:
    return ScheduleRun(
        id=run_id,
        schedule_id="s1",
        agent_id="a1",
        status=status,
        scheduled_for=_NOW,
        started_at=_NOW,
        finished_at=_NOW,
        session_id="sess-9",
        run_id="run-9",
        error_message=None,
        request_id="req-0",
    )


class TestListMyScheduleRuns:
    @pytest.mark.asyncio
    async def test_maps_tuples_to_responses(self):
        repo = MagicMock()
        repo.list_by_user = AsyncMock(
            return_value=[
                (_run("r1"), "아침 요약", "리서치 봇"),
                (_run("r2", status="failed"), "야간 집계", None),
            ]
        )
        uc = ListMyScheduleRunsUseCase(repo, MagicMock())
        items = await uc.execute("u1", 20, 0, "req-1")
        assert [i.id for i in items] == ["r1", "r2"]
        assert items[0].schedule_name == "아침 요약"
        assert items[0].agent_name == "리서치 봇"
        assert items[0].session_id == "sess-9"
        assert items[1].agent_name is None
        repo.list_by_user.assert_awaited_once_with("u1", 20, 0, "req-1")

    @pytest.mark.asyncio
    async def test_empty_history(self):
        repo = MagicMock()
        repo.list_by_user = AsyncMock(return_value=[])
        uc = ListMyScheduleRunsUseCase(repo, MagicMock())
        assert await uc.execute("u1", 20, 0, "req-1") == []
