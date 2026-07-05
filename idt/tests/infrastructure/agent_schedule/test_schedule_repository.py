"""Infrastructure 테스트: ScheduleRepository (Mock AsyncSession)."""
from datetime import date, datetime, time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.agent_schedule.entity import AgentSchedule
from src.domain.agent_schedule.value_objects import ScheduleSpec
from src.infrastructure.agent_schedule.models import AgentScheduleModel
from src.infrastructure.agent_schedule.schedule_repository import (
    ScheduleRepository,
    _to_entity,
)


@pytest.fixture
def mock_session():
    s = AsyncMock()
    s.add = MagicMock()  # add 는 sync 메서드
    return s


@pytest.fixture
def mock_logger():
    return MagicMock()


def _daily_model(**overrides) -> AgentScheduleModel:
    base = dict(
        id="s1",
        agent_id="a1",
        user_id="u1",
        name="아침 요약",
        schedule_type="daily",
        run_date=None,
        time_of_day=time(9, 0),
        days_of_week=None,
        cron_expr=None,
        instruction="{today} 시황 요약",
        enabled=True,
        timezone="Asia/Seoul",
        next_run_at=datetime(2026, 7, 2, 0, 0),
        last_run_at=None,
        created_at=datetime(2026, 7, 1, 0, 0),
        updated_at=datetime(2026, 7, 1, 0, 0),
    )
    base.update(overrides)
    return AgentScheduleModel(**base)


def _entity() -> AgentSchedule:
    return AgentSchedule(
        id="s1",
        agent_id="a1",
        user_id="u1",
        name="아침 요약",
        spec=ScheduleSpec(schedule_type="daily", time_of_day=time(9, 0)),
        instruction="{today} 시황 요약",
        enabled=True,
        timezone="Asia/Seoul",
        next_run_at=datetime(2026, 7, 2, 0, 0),
        last_run_at=None,
        created_at=datetime(2026, 7, 1, 0, 0),
        updated_at=datetime(2026, 7, 1, 0, 0),
    )


class TestToEntity:
    def test_maps_daily_model(self):
        entity = _to_entity(_daily_model())
        assert entity.spec.schedule_type == "daily"
        assert entity.spec.time_of_day == time(9, 0)
        assert entity.instruction == "{today} 시황 요약"

    def test_maps_weekly_days_list_to_tuple(self):
        model = _daily_model(
            schedule_type="weekly", days_of_week=[0, 2], time_of_day=time(9, 0)
        )
        entity = _to_entity(model)
        assert entity.spec.days_of_week == (0, 2)


class TestSave:
    @pytest.mark.asyncio
    async def test_save_adds_and_flushes(self, mock_session, mock_logger):
        repo = ScheduleRepository(session=mock_session, logger=mock_logger)
        await repo.save(_entity(), "req-1")
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()
        added = mock_session.add.call_args[0][0]
        assert isinstance(added, AgentScheduleModel)
        assert added.schedule_type == "daily"


class TestFindById:
    @pytest.mark.asyncio
    async def test_returns_entity_when_found(self, mock_session, mock_logger):
        mock_session.get = AsyncMock(return_value=_daily_model())
        repo = ScheduleRepository(session=mock_session, logger=mock_logger)
        found = await repo.find_by_id("s1", "req-1")
        assert found is not None and found.id == "s1"

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self, mock_session, mock_logger):
        mock_session.get = AsyncMock(return_value=None)
        repo = ScheduleRepository(session=mock_session, logger=mock_logger)
        assert await repo.find_by_id("nope", "req-1") is None


class TestListAndCount:
    @pytest.mark.asyncio
    async def test_list_by_agent_maps_results(self, mock_session, mock_logger):
        scalars = MagicMock()
        scalars.all.return_value = [_daily_model(), _daily_model(id="s2")]
        exec_result = MagicMock()
        exec_result.scalars.return_value = scalars
        mock_session.execute = AsyncMock(return_value=exec_result)
        repo = ScheduleRepository(session=mock_session, logger=mock_logger)
        result = await repo.list_by_agent("a1", "req-1")
        assert [s.id for s in result] == ["s1", "s2"]

    @pytest.mark.asyncio
    async def test_count_by_agent_returns_scalar(self, mock_session, mock_logger):
        exec_result = MagicMock()
        exec_result.scalar_one.return_value = 3
        mock_session.execute = AsyncMock(return_value=exec_result)
        repo = ScheduleRepository(session=mock_session, logger=mock_logger)
        assert await repo.count_by_agent("a1", "req-1") == 3


class TestUpdate:
    @pytest.mark.asyncio
    async def test_update_mutates_model_and_flushes(self, mock_session, mock_logger):
        model = _daily_model()
        mock_session.get = AsyncMock(return_value=model)
        repo = ScheduleRepository(session=mock_session, logger=mock_logger)
        entity = _entity()
        entity.name = "저녁 요약"
        entity.next_run_at = datetime(2026, 7, 3, 0, 0)
        await repo.update(entity, "req-1")
        assert model.name == "저녁 요약"
        assert model.next_run_at == datetime(2026, 7, 3, 0, 0)
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_missing_raises(self, mock_session, mock_logger):
        mock_session.get = AsyncMock(return_value=None)
        repo = ScheduleRepository(session=mock_session, logger=mock_logger)
        with pytest.raises(ValueError, match="찾을 수 없"):
            await repo.update(_entity(), "req-1")


class TestClaimDue:
    @pytest.mark.asyncio
    async def test_claim_recomputes_next_run_and_returns_scheduled_for(
        self, mock_session, mock_logger
    ):
        daily = _daily_model()  # next_run_at = 2026-07-02 00:00 (due)
        scalars = MagicMock()
        scalars.all.return_value = [daily]
        exec_result = MagicMock()
        exec_result.scalars.return_value = scalars
        mock_session.execute = AsyncMock(return_value=exec_result)

        repo = ScheduleRepository(session=mock_session, logger=mock_logger)
        now = datetime(2026, 7, 2, 0, 0, 30)
        claimed = await repo.claim_due(now, "req-1")

        assert len(claimed) == 1
        assert claimed[0].scheduled_for == datetime(2026, 7, 2, 0, 0)
        # 다음 09:00 KST = 07-03 00:00 UTC 로 재계산
        assert daily.next_run_at == datetime(2026, 7, 3, 0, 0)
        assert daily.enabled is True
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_claim_once_disables_schedule(self, mock_session, mock_logger):
        once = _daily_model(
            schedule_type="once",
            run_date=date(2026, 7, 2),
            time_of_day=time(9, 0),
        )
        scalars = MagicMock()
        scalars.all.return_value = [once]
        exec_result = MagicMock()
        exec_result.scalars.return_value = scalars
        mock_session.execute = AsyncMock(return_value=exec_result)

        repo = ScheduleRepository(session=mock_session, logger=mock_logger)
        claimed = await repo.claim_due(datetime(2026, 7, 2, 0, 0, 30), "req-1")

        assert len(claimed) == 1
        assert once.next_run_at is None
        assert once.enabled is False


class TestDeleteAndTouch:
    @pytest.mark.asyncio
    async def test_delete_executes_and_flushes(self, mock_session, mock_logger):
        mock_session.execute = AsyncMock()
        repo = ScheduleRepository(session=mock_session, logger=mock_logger)
        await repo.delete("s1", "req-1")
        mock_session.execute.assert_awaited_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_touch_last_run_executes_update(self, mock_session, mock_logger):
        mock_session.execute = AsyncMock()
        repo = ScheduleRepository(session=mock_session, logger=mock_logger)
        await repo.touch_last_run("s1", datetime(2026, 7, 2, 0, 1), "req-1")
        mock_session.execute.assert_awaited_once()
        mock_session.flush.assert_awaited_once()
