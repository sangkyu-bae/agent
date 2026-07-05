"""TriggerDueSchedulesUseCase 단위 테스트 — Mock 의존성."""
from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_schedule.trigger_due_schedules_use_case import (
    TriggerDueSchedulesUseCase,
)
from src.domain.agent_schedule.entity import AgentSchedule
from src.domain.agent_schedule.interfaces import ClaimedSchedule
from src.domain.agent_schedule.value_objects import ScheduleSpec


class _FakeCM:
    def __init__(self, value=None):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return False


def _schedule(schedule_id="s1", instruction="{today} 시황 요약") -> AgentSchedule:
    return AgentSchedule(
        id=schedule_id,
        agent_id="a1",
        user_id="u1",
        name="아침 요약",
        spec=ScheduleSpec(schedule_type="daily", time_of_day=time(9, 0)),
        instruction=instruction,
        enabled=True,
        timezone="Asia/Seoul",
        next_run_at=datetime(2026, 7, 3, 0, 0),
        last_run_at=None,
        created_at=datetime(2026, 7, 1, 0, 0),
        updated_at=datetime(2026, 7, 1, 0, 0),
    )


def _claimed(schedule_id="s1", **kw) -> ClaimedSchedule:
    return ClaimedSchedule(
        schedule=_schedule(schedule_id, **kw),
        scheduled_for=datetime(2026, 7, 2, 0, 0),
    )


def _make_uc(claimed: list[ClaimedSchedule], run_uc=None):
    session = AsyncMock()
    session.begin = MagicMock(return_value=_FakeCM())
    session_factory = MagicMock(return_value=_FakeCM(session))

    schedule_repo = MagicMock()
    schedule_repo.claim_due = AsyncMock(return_value=claimed)
    schedule_repo.touch_last_run = AsyncMock()

    if run_uc is None:
        run_uc = MagicMock()
        run_uc.execute = AsyncMock(
            return_value=MagicMock(session_id="sess-1", run_id="run-1")
        )

    sink = MagicMock()
    sink.on_started = AsyncMock(return_value="record-1")
    sink.on_finished = AsyncMock()

    uc = TriggerDueSchedulesUseCase(
        session_factory=session_factory,
        schedule_repo_builder=MagicMock(return_value=schedule_repo),
        run_agent_uc_builder=MagicMock(return_value=run_uc),
        sink=sink,
        logger=MagicMock(),
    )
    return uc, schedule_repo, run_uc, sink


class TestTriggerDueSchedules:
    @pytest.mark.asyncio
    async def test_no_due_schedules_runs_nothing(self):
        uc, _, run_uc, sink = _make_uc(claimed=[])
        result = await uc.execute("req-1")
        assert result.claimed == 0 and result.success == 0 and result.failed == 0
        run_uc.execute.assert_not_awaited()
        sink.on_started.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_two_due_schedules_all_succeed(self):
        uc, repo, run_uc, sink = _make_uc(
            claimed=[_claimed("s1"), _claimed("s2")]
        )
        result = await uc.execute("req-1")
        assert result.claimed == 2 and result.success == 2 and result.failed == 0
        assert run_uc.execute.await_count == 2
        assert sink.on_started.await_count == 2
        assert sink.on_finished.await_count == 2
        assert repo.touch_last_run.await_count == 2

    @pytest.mark.asyncio
    async def test_rendered_instruction_sent_as_query(self):
        uc, _, run_uc, _ = _make_uc(claimed=[_claimed()])
        await uc.execute("req-1")
        request = run_uc.execute.call_args[0][1]
        assert "{today}" not in request.query  # R9: 치환 완료된 실제 질문
        assert request.query.endswith("시황 요약")
        assert request.user_id == "u1"

    @pytest.mark.asyncio
    async def test_success_records_session_and_run_id(self):
        uc, _, _, sink = _make_uc(claimed=[_claimed()])
        await uc.execute("req-1")
        kwargs = sink.on_finished.call_args.kwargs
        assert sink.on_finished.call_args[0][1] == "success"
        assert kwargs["session_id"] == "sess-1"
        assert kwargs["run_id"] == "run-1"

    @pytest.mark.asyncio
    async def test_one_failure_isolated_others_continue(self):
        run_uc = MagicMock()
        run_uc.execute = AsyncMock(
            side_effect=[
                RuntimeError("boom"),
                MagicMock(session_id="sess-2", run_id="run-2"),
            ]
        )
        uc, _, _, sink = _make_uc(
            claimed=[_claimed("s1"), _claimed("s2")], run_uc=run_uc
        )
        result = await uc.execute("req-1")
        assert result.claimed == 2 and result.success == 1 and result.failed == 1
        statuses = [c[0][1] for c in sink.on_finished.call_args_list]
        assert statuses == ["failed", "success"]
        failed_kwargs = sink.on_finished.call_args_list[0].kwargs
        assert "boom" in failed_kwargs["error_message"]

    @pytest.mark.asyncio
    async def test_failed_run_also_touches_last_run(self):
        """A안: last_run_at 은 성공/실패 무관 '실행 시도' 시각을 기록한다."""
        run_uc = MagicMock()
        run_uc.execute = AsyncMock(side_effect=RuntimeError("boom"))
        uc, repo, _, _ = _make_uc(claimed=[_claimed("s1")], run_uc=run_uc)
        await uc.execute("req-1")
        repo.touch_last_run.assert_awaited_once()
        assert repo.touch_last_run.call_args[0][0] == "s1"

    @pytest.mark.asyncio
    async def test_status_snapshot_updated_after_execute(self):
        uc, _, _, _ = _make_uc(claimed=[_claimed()])
        assert uc.status().last_triggered_at is None
        await uc.execute("req-1")
        snapshot = uc.status()
        assert snapshot.last_triggered_at is not None
        assert snapshot.last_result.claimed == 1
