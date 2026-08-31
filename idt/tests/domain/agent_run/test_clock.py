"""domain/agent_run/clock 단위 테스트 (runtime-datetime-context D2).

순수 시각 계산: UTC → 로컬 변환(aware/naive 입력 호환) + 한국어 요일.
"""
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfoNotFoundError

import pytest
from src.domain.agent_run.clock import WEEKDAY_KO, to_local, weekday_ko


class TestToLocal:
    def test_utc_evening_is_next_day_in_kst(self):
        """FR-02 경계: UTC 2026-08-24 15:30 → KST 2026-08-25 00:30."""
        utc = datetime(2026, 8, 24, 15, 30, tzinfo=UTC)
        local = to_local(utc, "Asia/Seoul")
        assert local.date() == date(2026, 8, 25)
        assert local.hour == 0 and local.minute == 30

    def test_naive_input_is_treated_as_utc(self):
        """SchedulePolicy 규격(UTC naive)과 호환 — naive면 UTC로 간주."""
        naive = datetime(2026, 8, 24, 15, 30)
        assert to_local(naive, "Asia/Seoul").date() == date(2026, 8, 25)

    def test_aware_non_utc_input_is_converted_correctly(self):
        """이미 aware(KST)인 입력도 재해석 없이 변환."""
        from zoneinfo import ZoneInfo

        kst = datetime(2026, 8, 25, 0, 30, tzinfo=ZoneInfo("Asia/Seoul"))
        assert to_local(kst, "UTC").date() == date(2026, 8, 24)

    def test_invalid_timezone_raises(self):
        """잘못된 tz는 예외 전파 — degraded 처리는 application(render) 책임."""
        with pytest.raises(ZoneInfoNotFoundError):
            to_local(datetime(2026, 8, 25, tzinfo=UTC), "Mars/Olympus")


class TestWeekdayKo:
    def test_2026_08_25_is_tuesday(self):
        assert weekday_ko(date(2026, 8, 25)) == "화"

    def test_all_seven_days_map_in_order(self):
        # 2026-08-24(월) ~ 2026-08-30(일)
        days = [date(2026, 8, 24 + i) for i in range(7)]
        assert "".join(weekday_ko(d) for d in days) == WEEKDAY_KO == "월화수목금토일"
