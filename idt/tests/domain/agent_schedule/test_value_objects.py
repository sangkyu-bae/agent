"""ScheduleSpec VO 단위 테스트 — mock 금지."""
from datetime import date, time

import pytest

from src.domain.agent_schedule.value_objects import ScheduleSpec


class TestScheduleSpecOnce:
    def test_once_with_run_date_and_time_passes(self):
        spec = ScheduleSpec(
            schedule_type="once",
            run_date=date(2026, 12, 25),
            time_of_day=time(9, 0),
        )
        assert spec.schedule_type == "once"

    def test_once_without_run_date_raises(self):
        with pytest.raises(ValueError, match="run_date"):
            ScheduleSpec(schedule_type="once", time_of_day=time(9, 0))

    def test_once_without_time_of_day_raises(self):
        with pytest.raises(ValueError, match="time_of_day"):
            ScheduleSpec(schedule_type="once", run_date=date(2026, 12, 25))

    def test_once_with_cron_expr_raises(self):
        with pytest.raises(ValueError, match="cron_expr"):
            ScheduleSpec(
                schedule_type="once",
                run_date=date(2026, 12, 25),
                time_of_day=time(9, 0),
                cron_expr="0 9 * * *",
            )


class TestScheduleSpecDaily:
    def test_daily_with_time_passes(self):
        spec = ScheduleSpec(schedule_type="daily", time_of_day=time(9, 0))
        assert spec.time_of_day == time(9, 0)

    def test_daily_without_time_raises(self):
        with pytest.raises(ValueError, match="time_of_day"):
            ScheduleSpec(schedule_type="daily")

    def test_daily_with_days_of_week_raises(self):
        with pytest.raises(ValueError, match="days_of_week"):
            ScheduleSpec(
                schedule_type="daily", time_of_day=time(9, 0), days_of_week=(0,)
            )


class TestScheduleSpecWeekly:
    def test_weekly_with_days_and_time_passes(self):
        spec = ScheduleSpec(
            schedule_type="weekly", time_of_day=time(9, 0), days_of_week=(0, 2, 4)
        )
        assert spec.days_of_week == (0, 2, 4)

    def test_weekly_without_days_raises(self):
        with pytest.raises(ValueError, match="days_of_week"):
            ScheduleSpec(schedule_type="weekly", time_of_day=time(9, 0))

    def test_weekly_empty_days_raises(self):
        with pytest.raises(ValueError, match="days_of_week"):
            ScheduleSpec(
                schedule_type="weekly", time_of_day=time(9, 0), days_of_week=()
            )

    def test_weekly_out_of_range_day_raises(self):
        with pytest.raises(ValueError, match="0..6"):
            ScheduleSpec(
                schedule_type="weekly", time_of_day=time(9, 0), days_of_week=(0, 7)
            )

    def test_weekly_duplicate_days_raises(self):
        with pytest.raises(ValueError, match="중복"):
            ScheduleSpec(
                schedule_type="weekly", time_of_day=time(9, 0), days_of_week=(1, 1)
            )


class TestScheduleSpecCron:
    def test_cron_with_expr_passes(self):
        spec = ScheduleSpec(schedule_type="cron", cron_expr="0 9 * * 1-5")
        assert spec.cron_expr == "0 9 * * 1-5"

    def test_cron_without_expr_raises(self):
        with pytest.raises(ValueError, match="cron_expr"):
            ScheduleSpec(schedule_type="cron")

    def test_cron_with_time_of_day_raises(self):
        with pytest.raises(ValueError, match="time_of_day"):
            ScheduleSpec(
                schedule_type="cron", cron_expr="0 9 * * *", time_of_day=time(9, 0)
            )


class TestScheduleSpecType:
    def test_unknown_type_raises(self):
        with pytest.raises(ValueError, match="schedule_type"):
            ScheduleSpec(schedule_type="monthly", time_of_day=time(9, 0))

    def test_spec_is_immutable(self):
        spec = ScheduleSpec(schedule_type="daily", time_of_day=time(9, 0))
        with pytest.raises(Exception):
            spec.cron_expr = "0 9 * * *"
