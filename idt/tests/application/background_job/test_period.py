"""기간 필터 경계 계산 단위 테스트 (jobs-page-revamp Design §4.4).

DB 는 UTC naive 저장, 사용자 감각은 KST — 두 경계가 어긋나면 '오늘' 목록에서
항목이 통째로 누락된다. 경계값을 직접 고정해 회귀를 막는다.
"""
from datetime import datetime

import pytest

from src.application.background_job.period import period_to_utc_start

# 2026-09-03 10:30 UTC = 2026-09-03 19:30 KST (목요일)
_NOW = datetime(2026, 9, 3, 10, 30)


class TestPeriodToUtcStart:
    def test_all_has_no_lower_bound(self):
        assert period_to_utc_start("all", _NOW) is None

    def test_1h_is_relative(self):
        assert period_to_utc_start("1h", _NOW) == datetime(2026, 9, 3, 9, 30)

    def test_today_is_kst_midnight(self):
        # 2026-09-03 00:00 KST == 2026-09-02 15:00 UTC
        assert period_to_utc_start("today", _NOW) == datetime(2026, 9, 2, 15, 0)

    def test_week_is_kst_monday_midnight(self):
        # 목요일 → 같은 주 월요일 2026-08-31 00:00 KST == 2026-08-30 15:00 UTC
        assert period_to_utc_start("week", _NOW) == datetime(2026, 8, 30, 15, 0)

    def test_today_uses_kst_date_not_utc_date(self):
        """UTC 로는 아직 9/3 이지만 KST 로는 9/4 인 시각 — KST 날짜를 따라야 한다."""
        now = datetime(2026, 9, 3, 16, 0)  # KST 2026-09-04 01:00
        assert period_to_utc_start("today", now) == datetime(2026, 9, 3, 15, 0)

    def test_monday_early_morning_starts_same_day(self):
        """월요일 00:30 KST — 이번 주 시작은 지난주가 아니라 당일 자정이다."""
        now = datetime(2026, 8, 30, 15, 30)  # KST 2026-08-31(월) 00:30
        assert period_to_utc_start("week", now) == datetime(2026, 8, 30, 15, 0)

    def test_returns_naive_datetime(self):
        """DB 컬럼이 naive 이므로 tzinfo 가 남아 있으면 비교에서 터진다."""
        for period in ("1h", "today", "week"):
            assert period_to_utc_start(period, _NOW).tzinfo is None

    def test_unknown_period_rejected(self):
        with pytest.raises(ValueError):
            period_to_utc_start("month", _NOW)
