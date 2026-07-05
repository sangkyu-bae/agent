"""AgentSchedule / ScheduleRun 엔티티 + 인터페이스 계약 테스트 — mock 금지."""
from datetime import datetime, time

import pytest

from src.domain.agent_schedule.entity import AgentSchedule, ScheduleRun
from src.domain.agent_schedule.interfaces import (
    ScheduleRepositoryInterface,
    ScheduleRunRepositoryInterface,
    ScheduleRunSinkInterface,
)
from src.domain.agent_schedule.value_objects import ScheduleSpec


def _schedule(**overrides) -> AgentSchedule:
    base = dict(
        id="s1",
        agent_id="a1",
        user_id="u1",
        name="아침 요약",
        spec=ScheduleSpec(schedule_type="daily", time_of_day=time(9, 0)),
        instruction="{today} 시황 요약해줘",
        enabled=True,
        timezone="Asia/Seoul",
        next_run_at=datetime(2026, 7, 3, 0, 0),
        last_run_at=None,
        created_at=datetime(2026, 7, 2, 5, 0),
        updated_at=datetime(2026, 7, 2, 5, 0),
    )
    base.update(overrides)
    return AgentSchedule(**base)


class TestAgentScheduleEntity:
    def test_construct_with_all_fields(self):
        sch = _schedule()
        assert sch.id == "s1"
        assert sch.spec.schedule_type == "daily"
        assert sch.instruction == "{today} 시황 요약해줘"

    def test_next_run_at_none_allowed(self):
        sch = _schedule(next_run_at=None, enabled=False)
        assert sch.next_run_at is None


class TestScheduleRunEntity:
    def test_construct_running(self):
        run = ScheduleRun(
            id="r1",
            schedule_id="s1",
            agent_id="a1",
            status="running",
            scheduled_for=datetime(2026, 7, 3, 0, 0),
            started_at=datetime(2026, 7, 3, 0, 0, 5),
            finished_at=None,
            session_id=None,
            run_id=None,
            error_message=None,
            request_id="req-1",
        )
        assert run.status == "running"


class TestInterfacesAreAbstract:
    @pytest.mark.parametrize(
        "iface",
        [
            ScheduleRepositoryInterface,
            ScheduleRunRepositoryInterface,
            ScheduleRunSinkInterface,
        ],
    )
    def test_cannot_instantiate(self, iface):
        with pytest.raises(TypeError):
            iface()
