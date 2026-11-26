"""스케줄 응답 시각은 UTC 오프셋을 붙여 보낸다.

DB 는 UTC naive 를 저장한다. 오프셋 없이 보내면 프론트 new Date() 가 로컬(KST)
시각으로 읽어 9시간 이르게 보인다(실측: 11:50 회차가 02:50 으로 표시).
승인 API(_utc_iso, approval-gate G12)와 같은 규칙을 스케줄 응답에도 적용한다.
"""
from datetime import UTC, datetime, time

from src.application.agent_schedule.schemas import (
    ScheduleResponse,
    ScheduleRunResponse,
)
from src.application.background_job.schemas import (
    MyScheduleResponse,
    MyScheduleRunResponse,
)
from src.domain.agent_schedule.entity import AgentSchedule, ScheduleRun
from src.domain.agent_schedule.value_objects import ScheduleSpec

NAIVE = datetime(2026, 11, 25, 2, 50, 0)  # = KST 11:50


def _schedule(**overrides) -> AgentSchedule:
    base = dict(
        id="s1",
        agent_id="a1",
        user_id="7",
        name="10분 점검",
        spec=ScheduleSpec(schedule_type="daily", time_of_day=time(9, 0)),
        instruction="점검",
        enabled=True,
        timezone="Asia/Seoul",
        next_run_at=NAIVE,
        last_run_at=NAIVE,
        created_at=NAIVE,
        updated_at=NAIVE,
    )
    base.update(overrides)
    return AgentSchedule(**base)


def _run(**overrides) -> ScheduleRun:
    base = dict(
        id="r1",
        schedule_id="s1",
        agent_id="a1",
        status="skipped",
        scheduled_for=NAIVE,
        started_at=NAIVE,
        finished_at=NAIVE,
        session_id=None,
        run_id=None,
        error_message=None,
        request_id="req",
        skip_reason="approval_pending",
    )
    base.update(overrides)
    return ScheduleRun(**base)


def _parsed(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None, value
    return parsed


class TestScheduleResponseUtc:
    def test_all_times_carry_utc_offset(self):
        res = ScheduleResponse.from_entity(_schedule())
        for v in (res.next_run_at, res.last_run_at, res.created_at, res.updated_at):
            assert v == "2026-11-25T02:50:00+00:00"

    def test_none_stays_none(self):
        res = ScheduleResponse.from_entity(
            _schedule(next_run_at=None, last_run_at=None)
        )
        assert res.next_run_at is None and res.last_run_at is None

    def test_aware_value_is_kept_as_same_instant(self):
        aware = NAIVE.replace(tzinfo=UTC)
        res = ScheduleResponse.from_entity(_schedule(next_run_at=aware))
        assert _parsed(res.next_run_at) == aware


class TestScheduleRunResponseUtc:
    def test_all_times_carry_utc_offset(self):
        res = ScheduleRunResponse.from_entity(_run())
        for v in (res.scheduled_for, res.started_at, res.finished_at):
            assert v == "2026-11-25T02:50:00+00:00"

    def test_unfinished_run_keeps_none(self):
        res = ScheduleRunResponse.from_entity(_run(finished_at=None))
        assert res.finished_at is None


class TestJobsInboxScheduleUtc:
    """작업함(백그라운드 잡) 화면의 스케줄 목록·이력도 같은 규칙."""

    def test_my_schedule_reuses_utc_times(self):
        res = MyScheduleResponse.from_entity(_schedule(), agent_name="에이전트")
        assert res.next_run_at == "2026-11-25T02:50:00+00:00"
        assert res.last_run_at == "2026-11-25T02:50:00+00:00"

    def test_my_schedule_run_serializes_with_offset(self):
        res = MyScheduleRunResponse(
            id="r1",
            schedule_id="s1",
            schedule_name="10분 점검",
            agent_id="a1",
            status="skipped",
            scheduled_for=NAIVE,
            started_at=NAIVE,
            finished_at=None,
            session_id=None,
            error_message=None,
        )
        body = res.model_dump(mode="json")
        assert body["scheduled_for"] == "2026-11-25T02:50:00+00:00"
        assert body["started_at"] == "2026-11-25T02:50:00+00:00"
        assert body["finished_at"] is None
