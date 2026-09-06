"""내 스케줄 정의 조회 use case 단위 테스트 (jobs-page-revamp FR-15)."""
from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.background_job.list_my_schedules_use_case import (
    ListMySchedulesUseCase,
)
from src.domain.agent_schedule.entity import AgentSchedule
from src.domain.agent_schedule.value_objects import ScheduleSpec

_NOW = datetime(2026, 9, 4, 1, 0)


def _schedule(schedule_id="s1", agent_id="a1", enabled=True) -> AgentSchedule:
    return AgentSchedule(
        id=schedule_id,
        agent_id=agent_id,
        user_id="u1",
        name="아침 요약",
        spec=ScheduleSpec(
            schedule_type="daily",
            run_date=None,
            time_of_day=time(9, 0),
            days_of_week=None,
            cron_expr=None,
        ),
        instruction="오늘 뉴스 요약해줘",
        enabled=enabled,
        timezone="Asia/Seoul",
        next_run_at=_NOW,
        last_run_at=None,
        created_at=_NOW,
        updated_at=_NOW,
    )


class TestListMySchedules:
    @pytest.mark.asyncio
    async def test_maps_schedules_with_agent_name(self):
        repo = MagicMock()
        repo.list_by_user = AsyncMock(
            return_value=[
                (_schedule("s1"), "리서치 봇"),
                (_schedule("s2", agent_id="a2"), None),
            ]
        )
        uc = ListMySchedulesUseCase(repo, MagicMock())
        items = await uc.execute("u1", "req-1")
        assert [i.id for i in items] == ["s1", "s2"]
        assert items[0].agent_name == "리서치 봇"
        # 에이전트가 삭제돼도 스케줄 행은 사라지지 않는다
        assert items[1].agent_name is None
        repo.list_by_user.assert_awaited_once_with("u1", "req-1")

    @pytest.mark.asyncio
    async def test_exposes_fields_needed_by_schedule_tab(self):
        repo = MagicMock()
        repo.list_by_user = AsyncMock(return_value=[(_schedule(), "리서치 봇")])
        uc = ListMySchedulesUseCase(repo, MagicMock())
        item = (await uc.execute("u1", "req-1"))[0]
        # 관리(토글·삭제)는 /agents/{id}/schedules 경로를 조립해야 하므로 agent_id 필수
        assert item.agent_id == "a1"
        assert item.name == "아침 요약"
        assert item.spec.schedule_type == "daily"
        assert item.enabled is True
        assert item.next_run_at is not None

    @pytest.mark.asyncio
    async def test_empty_list(self):
        repo = MagicMock()
        repo.list_by_user = AsyncMock(return_value=[])
        uc = ListMySchedulesUseCase(repo, MagicMock())
        assert await uc.execute("u1", "req-1") == []
