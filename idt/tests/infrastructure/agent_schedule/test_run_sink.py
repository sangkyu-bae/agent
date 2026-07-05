"""Infrastructure 테스트: ScheduleRunRepository + DbScheduleRunSink (Mock)."""
from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.agent_schedule.entity import AgentSchedule, ScheduleRun
from src.domain.agent_schedule.value_objects import ScheduleSpec
from src.infrastructure.agent_schedule.models import AgentScheduleRunModel
from src.infrastructure.agent_schedule.run_sink import DbScheduleRunSink
from src.infrastructure.agent_schedule.schedule_run_repository import (
    ScheduleRunRepository,
)


@pytest.fixture
def mock_session():
    s = AsyncMock()
    s.add = MagicMock()
    return s


@pytest.fixture
def mock_logger():
    return MagicMock()


class _FakeCM:
    """async context manager: 진입 시 지정 값 반환."""

    def __init__(self, value=None):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return False


def _make_session_factory(session):
    session.begin = MagicMock(return_value=_FakeCM())
    return MagicMock(return_value=_FakeCM(session))


def _schedule() -> AgentSchedule:
    return AgentSchedule(
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
        created_at=datetime(2026, 7, 1, 0, 0),
        updated_at=datetime(2026, 7, 1, 0, 0),
    )


def _run_model(**overrides) -> AgentScheduleRunModel:
    base = dict(
        id="r1",
        schedule_id="s1",
        agent_id="a1",
        status="running",
        scheduled_for=datetime(2026, 7, 2, 0, 0),
        started_at=datetime(2026, 7, 2, 0, 0, 5),
        finished_at=None,
        session_id=None,
        run_id=None,
        error_message=None,
        request_id="req-1",
    )
    base.update(overrides)
    return AgentScheduleRunModel(**base)


class TestScheduleRunRepository:
    @pytest.mark.asyncio
    async def test_save_adds_and_flushes(self, mock_session, mock_logger):
        repo = ScheduleRunRepository(session=mock_session, logger=mock_logger)
        run = ScheduleRun(
            id="r1",
            schedule_id="s1",
            agent_id="a1",
            status="running",
            scheduled_for=datetime(2026, 7, 2, 0, 0),
            started_at=datetime(2026, 7, 2, 0, 0, 5),
            finished_at=None,
            session_id=None,
            run_id=None,
            error_message=None,
            request_id="req-1",
        )
        await repo.save(run, "req-1")
        mock_session.add.assert_called_once()
        assert isinstance(mock_session.add.call_args[0][0], AgentScheduleRunModel)
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_by_schedule_maps_results(self, mock_session, mock_logger):
        scalars = MagicMock()
        scalars.all.return_value = [_run_model(), _run_model(id="r2")]
        exec_result = MagicMock()
        exec_result.scalars.return_value = scalars
        mock_session.execute = AsyncMock(return_value=exec_result)
        repo = ScheduleRunRepository(session=mock_session, logger=mock_logger)
        runs = await repo.list_by_schedule("s1", 20, 0, "req-1")
        assert [r.id for r in runs] == ["r1", "r2"]


class TestDbScheduleRunSink:
    @pytest.mark.asyncio
    async def test_on_started_inserts_running_record(self, mock_session, mock_logger):
        factory = _make_session_factory(mock_session)
        sink = DbScheduleRunSink(session_factory=factory, logger=mock_logger)

        run_record_id = await sink.on_started(
            _schedule(), scheduled_for=datetime(2026, 7, 2, 0, 0), request_id="req-1"
        )

        assert isinstance(run_record_id, str) and run_record_id
        added = mock_session.add.call_args[0][0]
        assert added.status == "running"
        assert added.schedule_id == "s1"
        assert added.agent_id == "a1"

    @pytest.mark.asyncio
    async def test_on_finished_success_updates_record(self, mock_session, mock_logger):
        model = _run_model()
        mock_session.get = AsyncMock(return_value=model)
        factory = _make_session_factory(mock_session)
        sink = DbScheduleRunSink(session_factory=factory, logger=mock_logger)

        await sink.on_finished(
            "r1", "success", "req-1", session_id="sess-1", run_id="run-1"
        )

        assert model.status == "success"
        assert model.session_id == "sess-1"
        assert model.run_id == "run-1"
        assert model.finished_at is not None

    @pytest.mark.asyncio
    async def test_on_finished_failed_records_error(self, mock_session, mock_logger):
        model = _run_model()
        mock_session.get = AsyncMock(return_value=model)
        factory = _make_session_factory(mock_session)
        sink = DbScheduleRunSink(session_factory=factory, logger=mock_logger)

        await sink.on_finished("r1", "failed", "req-1", error_message="boom")

        assert model.status == "failed"
        assert model.error_message == "boom"
