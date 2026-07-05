"""agent-schedule CRUD UseCase 단위 테스트 — Mock 의존성."""
from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_schedule.create_schedule_use_case import (
    CreateScheduleUseCase,
)
from src.application.agent_schedule.delete_schedule_use_case import (
    DeleteScheduleUseCase,
)
from src.application.agent_schedule.get_schedule_use_case import GetScheduleUseCase
from src.application.agent_schedule.list_schedule_runs_use_case import (
    ListScheduleRunsUseCase,
)
from src.application.agent_schedule.list_schedules_use_case import (
    ListSchedulesUseCase,
)
from src.application.agent_schedule.schemas import (
    CreateScheduleRequest,
    ScheduleSpecPayload,
)
from src.application.agent_schedule.toggle_schedule_use_case import (
    ToggleScheduleUseCase,
)
from src.application.agent_schedule.update_schedule_use_case import (
    UpdateScheduleUseCase,
)
from src.domain.agent_schedule.entity import AgentSchedule, ScheduleRun
from src.domain.agent_schedule.value_objects import ScheduleSpec

NOW = datetime(2026, 7, 2, 5, 0)


def _agent(user_id="u1"):
    agent = MagicMock()
    agent.user_id = user_id
    return agent


def _schedule(**overrides) -> AgentSchedule:
    base = dict(
        id="s1",
        agent_id="a1",
        user_id="u1",
        name="아침 요약",
        spec=ScheduleSpec(schedule_type="daily", time_of_day=time(9, 0)),
        instruction="{today} 요약",
        enabled=True,
        timezone="Asia/Seoul",
        next_run_at=datetime(2026, 7, 3, 0, 0),
        last_run_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    base.update(overrides)
    return AgentSchedule(**base)


def _create_request(**overrides) -> CreateScheduleRequest:
    base = dict(
        name="아침 요약",
        spec=ScheduleSpecPayload(schedule_type="daily", time_of_day=time(9, 0)),
        instruction="{today} 시황 요약해줘",
        timezone="Asia/Seoul",
        enabled=True,
    )
    base.update(overrides)
    return CreateScheduleRequest(**base)


def _mocks():
    schedule_repo = MagicMock()
    schedule_repo.save = AsyncMock()
    schedule_repo.find_by_id = AsyncMock(return_value=_schedule())
    schedule_repo.list_by_agent = AsyncMock(return_value=[_schedule()])
    schedule_repo.count_by_agent = AsyncMock(return_value=0)
    schedule_repo.update = AsyncMock()
    schedule_repo.delete = AsyncMock()
    agent_repo = MagicMock()
    agent_repo.find_by_id = AsyncMock(return_value=_agent("u1"))
    logger = MagicMock()
    return schedule_repo, agent_repo, logger


class TestCreateScheduleUseCase:
    @pytest.mark.asyncio
    async def test_create_owner_saves_with_next_run(self):
        schedule_repo, agent_repo, logger = _mocks()
        uc = CreateScheduleUseCase(schedule_repo, agent_repo, logger)
        resp = await uc.execute("a1", "u1", _create_request(), "req-1")
        schedule_repo.save.assert_awaited_once()
        saved: AgentSchedule = schedule_repo.save.call_args[0][0]
        assert saved.next_run_at is not None
        assert resp.agent_id == "a1"
        assert resp.instruction == "{today} 시황 요약해줘"

    @pytest.mark.asyncio
    async def test_create_agent_not_found_raises(self):
        schedule_repo, agent_repo, logger = _mocks()
        agent_repo.find_by_id = AsyncMock(return_value=None)
        uc = CreateScheduleUseCase(schedule_repo, agent_repo, logger)
        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute("a1", "u1", _create_request(), "req-1")

    @pytest.mark.asyncio
    async def test_create_non_owner_agent_forbidden(self):
        schedule_repo, agent_repo, logger = _mocks()
        agent_repo.find_by_id = AsyncMock(return_value=_agent("other"))
        uc = CreateScheduleUseCase(schedule_repo, agent_repo, logger)
        with pytest.raises(PermissionError):
            await uc.execute("a1", "u1", _create_request(), "req-1")

    @pytest.mark.asyncio
    async def test_create_over_limit_raises(self):
        schedule_repo, agent_repo, logger = _mocks()
        schedule_repo.count_by_agent = AsyncMock(return_value=10)
        uc = CreateScheduleUseCase(schedule_repo, agent_repo, logger)
        with pytest.raises(ValueError, match="10"):
            await uc.execute("a1", "u1", _create_request(), "req-1")

    @pytest.mark.asyncio
    async def test_create_dense_cron_raises(self):
        schedule_repo, agent_repo, logger = _mocks()
        uc = CreateScheduleUseCase(schedule_repo, agent_repo, logger)
        req = _create_request(
            spec=ScheduleSpecPayload(schedule_type="cron", cron_expr="* * * * *")
        )
        with pytest.raises(ValueError, match="10분"):
            await uc.execute("a1", "u1", req, "req-1")


class TestListSchedulesUseCase:
    @pytest.mark.asyncio
    async def test_list_owner_returns_schedules(self):
        schedule_repo, agent_repo, logger = _mocks()
        uc = ListSchedulesUseCase(schedule_repo, agent_repo, logger)
        result = await uc.execute("a1", "u1", "req-1")
        assert len(result) == 1 and result[0].id == "s1"

    @pytest.mark.asyncio
    async def test_list_non_owner_forbidden(self):
        schedule_repo, agent_repo, logger = _mocks()
        agent_repo.find_by_id = AsyncMock(return_value=_agent("other"))
        uc = ListSchedulesUseCase(schedule_repo, agent_repo, logger)
        with pytest.raises(PermissionError):
            await uc.execute("a1", "u1", "req-1")


class TestGetScheduleUseCase:
    @pytest.mark.asyncio
    async def test_get_owner_returns_schedule(self):
        schedule_repo, _, logger = _mocks()
        uc = GetScheduleUseCase(schedule_repo, logger)
        resp = await uc.execute("a1", "s1", "u1", "req-1")
        assert resp.id == "s1"

    @pytest.mark.asyncio
    async def test_get_not_found_raises(self):
        schedule_repo, _, logger = _mocks()
        schedule_repo.find_by_id = AsyncMock(return_value=None)
        uc = GetScheduleUseCase(schedule_repo, logger)
        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute("a1", "s1", "u1", "req-1")

    @pytest.mark.asyncio
    async def test_get_agent_mismatch_raises(self):
        schedule_repo, _, logger = _mocks()
        uc = GetScheduleUseCase(schedule_repo, logger)
        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute("other-agent", "s1", "u1", "req-1")

    @pytest.mark.asyncio
    async def test_get_non_owner_forbidden(self):
        schedule_repo, _, logger = _mocks()
        uc = GetScheduleUseCase(schedule_repo, logger)
        with pytest.raises(PermissionError):
            await uc.execute("a1", "s1", "intruder", "req-1")


class TestUpdateScheduleUseCase:
    @pytest.mark.asyncio
    async def test_update_recomputes_next_run_on_spec_change(self):
        schedule_repo, _, logger = _mocks()
        uc = UpdateScheduleUseCase(schedule_repo, logger)
        req = _create_request(
            spec=ScheduleSpecPayload(schedule_type="daily", time_of_day=time(18, 0))
        )
        resp = await uc.execute("a1", "s1", "u1", req, "req-1")
        schedule_repo.update.assert_awaited_once()
        updated: AgentSchedule = schedule_repo.update.call_args[0][0]
        assert updated.spec.time_of_day == time(18, 0)
        # 18:00 KST = 09:00 UTC 로 재계산됨
        assert updated.next_run_at.hour == 9
        assert resp.name == "아침 요약"

    @pytest.mark.asyncio
    async def test_update_non_owner_forbidden(self):
        schedule_repo, _, logger = _mocks()
        uc = UpdateScheduleUseCase(schedule_repo, logger)
        with pytest.raises(PermissionError):
            await uc.execute("a1", "s1", "intruder", _create_request(), "req-1")


class TestDeleteScheduleUseCase:
    @pytest.mark.asyncio
    async def test_delete_owner_deletes(self):
        schedule_repo, _, logger = _mocks()
        uc = DeleteScheduleUseCase(schedule_repo, logger)
        await uc.execute("a1", "s1", "u1", "req-1")
        schedule_repo.delete.assert_awaited_once_with("s1", "req-1")

    @pytest.mark.asyncio
    async def test_delete_non_owner_forbidden(self):
        schedule_repo, _, logger = _mocks()
        uc = DeleteScheduleUseCase(schedule_repo, logger)
        with pytest.raises(PermissionError):
            await uc.execute("a1", "s1", "intruder", "req-1")


class TestToggleScheduleUseCase:
    @pytest.mark.asyncio
    async def test_enable_recomputes_next_run(self):
        schedule_repo, _, logger = _mocks()
        stale = _schedule(enabled=False, next_run_at=datetime(2020, 1, 1))
        schedule_repo.find_by_id = AsyncMock(return_value=stale)
        uc = ToggleScheduleUseCase(schedule_repo, logger)
        resp = await uc.execute("a1", "s1", "u1", True, "req-1")
        updated: AgentSchedule = schedule_repo.update.call_args[0][0]
        assert updated.enabled is True
        assert updated.next_run_at > datetime(2026, 1, 1)  # 과거 시각으로 즉시 폭발 방지
        assert resp.enabled is True

    @pytest.mark.asyncio
    async def test_disable_keeps_next_run(self):
        schedule_repo, _, logger = _mocks()
        uc = ToggleScheduleUseCase(schedule_repo, logger)
        await uc.execute("a1", "s1", "u1", False, "req-1")
        updated: AgentSchedule = schedule_repo.update.call_args[0][0]
        assert updated.enabled is False
        assert updated.next_run_at == datetime(2026, 7, 3, 0, 0)


class TestListScheduleRunsUseCase:
    @pytest.mark.asyncio
    async def test_list_runs_owner_returns_history(self):
        schedule_repo, _, logger = _mocks()
        run_repo = MagicMock()
        run_repo.list_by_schedule = AsyncMock(
            return_value=[
                ScheduleRun(
                    id="r1",
                    schedule_id="s1",
                    agent_id="a1",
                    status="success",
                    scheduled_for=datetime(2026, 7, 2, 0, 0),
                    started_at=datetime(2026, 7, 2, 0, 0, 5),
                    finished_at=datetime(2026, 7, 2, 0, 1),
                    session_id="sess-1",
                    run_id="run-1",
                    error_message=None,
                    request_id="req-0",
                )
            ]
        )
        uc = ListScheduleRunsUseCase(schedule_repo, run_repo, logger)
        result = await uc.execute("a1", "s1", "u1", 20, 0, "req-1")
        assert len(result) == 1 and result[0].status == "success"

    @pytest.mark.asyncio
    async def test_list_runs_limit_capped_at_100(self):
        schedule_repo, _, logger = _mocks()
        run_repo = MagicMock()
        run_repo.list_by_schedule = AsyncMock(return_value=[])
        uc = ListScheduleRunsUseCase(schedule_repo, run_repo, logger)
        await uc.execute("a1", "s1", "u1", 500, 0, "req-1")
        assert run_repo.list_by_schedule.call_args[0][1] == 100
