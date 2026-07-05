"""SchedulePolicy 단위 테스트 — mock 금지.

시각 규격: 입력/출력 datetime 은 모두 UTC naive.
KST(Asia/Seoul, UTC+9) 기준 계산 검증 포함.
참고: 2026-07-02 는 목요일.
"""
from datetime import date, datetime, time

import pytest

from src.domain.agent_schedule.policies import SchedulePolicy
from src.domain.agent_schedule.value_objects import ScheduleSpec

KST = "Asia/Seoul"


def _daily(t: time) -> ScheduleSpec:
    return ScheduleSpec(schedule_type="daily", time_of_day=t)


class TestComputeNextRunDaily:
    def test_daily_after_time_passed_returns_tomorrow(self):
        # KST 2026-07-02 14:00 (UTC 05:00) → 다음 09:00 KST = 07-03 00:00 UTC
        nxt = SchedulePolicy.compute_next_run(
            _daily(time(9, 0)), KST, after_utc=datetime(2026, 7, 2, 5, 0)
        )
        assert nxt == datetime(2026, 7, 3, 0, 0)

    def test_daily_before_time_returns_today(self):
        # KST 2026-07-02 07:00 (UTC 07-01 22:00) → 오늘 09:00 KST = 07-02 00:00 UTC
        nxt = SchedulePolicy.compute_next_run(
            _daily(time(9, 0)), KST, after_utc=datetime(2026, 7, 1, 22, 0)
        )
        assert nxt == datetime(2026, 7, 2, 0, 0)

    def test_daily_kst_midnight_boundary_crosses_utc_date(self):
        # KST 00:30 은 UTC 전날 15:30 — 날짜 경계 검증
        nxt = SchedulePolicy.compute_next_run(
            _daily(time(0, 30)), KST, after_utc=datetime(2026, 7, 2, 10, 0)
        )
        assert nxt == datetime(2026, 7, 2, 15, 30)


class TestComputeNextRunWeekly:
    def test_weekly_next_monday_from_thursday(self):
        spec = ScheduleSpec(
            schedule_type="weekly", time_of_day=time(9, 0), days_of_week=(0,)
        )
        # 목요일 KST 14:00 → 다음 월요일 07-06 09:00 KST = 07-06 00:00 UTC
        nxt = SchedulePolicy.compute_next_run(
            spec, KST, after_utc=datetime(2026, 7, 2, 5, 0)
        )
        assert nxt == datetime(2026, 7, 6, 0, 0)

    def test_weekly_same_day_time_not_passed_returns_today(self):
        spec = ScheduleSpec(
            schedule_type="weekly", time_of_day=time(23, 0), days_of_week=(3,)
        )
        # 목요일(=3) KST 14:00 → 오늘 23:00 KST = 07-02 14:00 UTC
        nxt = SchedulePolicy.compute_next_run(
            spec, KST, after_utc=datetime(2026, 7, 2, 5, 0)
        )
        assert nxt == datetime(2026, 7, 2, 14, 0)


class TestComputeNextRunOnce:
    def test_once_future_returns_run_datetime(self):
        spec = ScheduleSpec(
            schedule_type="once", run_date=date(2026, 12, 25), time_of_day=time(9, 0)
        )
        nxt = SchedulePolicy.compute_next_run(
            spec, KST, after_utc=datetime(2026, 7, 2, 5, 0)
        )
        assert nxt == datetime(2026, 12, 25, 0, 0)

    def test_once_past_returns_none(self):
        spec = ScheduleSpec(
            schedule_type="once", run_date=date(2026, 1, 1), time_of_day=time(9, 0)
        )
        nxt = SchedulePolicy.compute_next_run(
            spec, KST, after_utc=datetime(2026, 7, 2, 5, 0)
        )
        assert nxt is None


class TestComputeNextRunCron:
    def test_cron_daily_nine_am_kst(self):
        spec = ScheduleSpec(schedule_type="cron", cron_expr="0 9 * * *")
        nxt = SchedulePolicy.compute_next_run(
            spec, KST, after_utc=datetime(2026, 7, 2, 5, 0)
        )
        assert nxt == datetime(2026, 7, 3, 0, 0)


class TestValidateSpec:
    NOW = datetime(2026, 7, 2, 5, 0)

    def test_valid_daily_passes(self):
        SchedulePolicy.validate_spec(_daily(time(9, 0)), KST, self.NOW)

    def test_invalid_cron_expr_raises(self):
        spec = ScheduleSpec(schedule_type="cron", cron_expr="not a cron")
        with pytest.raises(ValueError, match="cron"):
            SchedulePolicy.validate_spec(spec, KST, self.NOW)

    def test_dense_cron_under_min_interval_raises(self):
        spec = ScheduleSpec(schedule_type="cron", cron_expr="*/5 * * * *")
        with pytest.raises(ValueError, match="10"):
            SchedulePolicy.validate_spec(spec, KST, self.NOW)

    def test_hourly_cron_passes(self):
        spec = ScheduleSpec(schedule_type="cron", cron_expr="0 * * * *")
        SchedulePolicy.validate_spec(spec, KST, self.NOW)

    def test_once_in_past_raises(self):
        spec = ScheduleSpec(
            schedule_type="once", run_date=date(2026, 1, 1), time_of_day=time(9, 0)
        )
        with pytest.raises(ValueError, match="미래"):
            SchedulePolicy.validate_spec(spec, KST, self.NOW)

    def test_invalid_timezone_raises(self):
        with pytest.raises(ValueError, match="timezone"):
            SchedulePolicy.validate_spec(_daily(time(9, 0)), "Not/AZone", self.NOW)


class TestRenderInstruction:
    # UTC 2026-07-02 16:00 = KST 2026-07-03 01:00 (금요일)
    NOW = datetime(2026, 7, 2, 16, 0)

    def test_render_today_placeholder(self):
        out = SchedulePolicy.render_instruction("{today} 시황 요약", KST, self.NOW)
        assert out == "2026-07-03 시황 요약"

    def test_render_now_placeholder(self):
        out = SchedulePolicy.render_instruction("현재 {now} 기준", KST, self.NOW)
        assert out == "현재 01:00 기준"

    def test_render_weekday_placeholder(self):
        out = SchedulePolicy.render_instruction("{weekday}요일 보고", KST, self.NOW)
        assert out == "금요일 보고"

    def test_render_unknown_placeholder_kept(self):
        out = SchedulePolicy.render_instruction("{foo} 유지 {today}", KST, self.NOW)
        assert out == "{foo} 유지 2026-07-03"

    def test_render_no_placeholder_unchanged(self):
        out = SchedulePolicy.render_instruction("그냥 질문", KST, self.NOW)
        assert out == "그냥 질문"

    def test_render_truncates_over_2000_chars(self):
        out = SchedulePolicy.render_instruction("a" * 2500, KST, self.NOW)
        assert len(out) == 2000


class TestOwnershipAndCount:
    def test_can_modify_owner_true(self):
        assert SchedulePolicy.can_modify("u1", "u1") is True

    def test_can_modify_other_false(self):
        assert SchedulePolicy.can_modify("u1", "u2") is False

    def test_validate_count_under_limit_passes(self):
        SchedulePolicy.validate_count(9)

    def test_validate_count_at_limit_raises(self):
        with pytest.raises(ValueError, match="10"):
            SchedulePolicy.validate_count(10)


class TestValidateInstruction:
    def test_normal_instruction_passes(self):
        SchedulePolicy.validate_instruction("매일 시황 요약해줘")

    def test_empty_instruction_raises(self):
        with pytest.raises(ValueError, match="비어"):
            SchedulePolicy.validate_instruction("   ")

    def test_over_limit_instruction_raises(self):
        with pytest.raises(ValueError, match="1900"):
            SchedulePolicy.validate_instruction("a" * 1901)
