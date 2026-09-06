"""기간 필터 경계 계산 (jobs-page-revamp Design §4.4).

DB 는 UTC naive 저장, 사용자가 말하는 '오늘'·'이번 주'는 KST 기준이다.
경계 환산은 정책성 계산이므로 라우터·리포지토리가 아닌 Application 에 둔다.
"""
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

PERIOD_ALL = "all"
PERIOD_1H = "1h"
PERIOD_TODAY = "today"
PERIOD_WEEK = "week"

ALLOWED_PERIODS = (PERIOD_ALL, PERIOD_1H, PERIOD_TODAY, PERIOD_WEEK)


def period_to_utc_start(period: str, now_utc: datetime) -> datetime | None:
    """기간 코드 → 조회 하한(UTC naive). 'all' 이면 하한 없음(None).

    Plan SC: FR-09 — 기준 시각은 job=queued_at, 스케줄=scheduled_for.
    """
    if period == PERIOD_ALL:
        return None
    if period not in ALLOWED_PERIODS:
        raise ValueError(f"지원하지 않는 기간 필터입니다: {period}")

    now_kst = now_utc.replace(tzinfo=timezone.utc).astimezone(KST)
    if period == PERIOD_1H:
        start_kst = now_kst - timedelta(hours=1)
    elif period == PERIOD_TODAY:
        start_kst = _kst_midnight(now_kst)
    else:  # PERIOD_WEEK — KST 기준 월요일 00:00
        start_kst = _kst_midnight(now_kst - timedelta(days=now_kst.weekday()))

    return start_kst.astimezone(timezone.utc).replace(tzinfo=None)


def _kst_midnight(moment_kst: datetime) -> datetime:
    return moment_kst.replace(hour=0, minute=0, second=0, microsecond=0)
