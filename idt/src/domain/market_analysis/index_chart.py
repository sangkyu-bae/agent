"""지수 YTD 차트 순수 규칙 — 꼬리 범위 · 구간 나누기 · 연초 대비 등락률.

Design Ref: market-index-ytd-chart §3.1
- 확정 봉은 되돌아가 바뀌지 않으므로 "마지막 저장일 다음 날 ~ 오늘" 꼬리만 받는다.
- KIS get_index_history 는 한 번에 최대 200봉 → 반기(183일 ≈ 125거래일) 구간으로 나눈다.
- 등락률은 연초 첫 봉 종가 대비 %, 소수 2자리 ROUND_HALF_UP (LLM·프론트 계산 없음).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

INDEXES: tuple[str, ...] = ("KOSPI", "KOSDAQ")
CHUNK_DAYS = 183
FETCH_LIMIT = 200
_RATE_Q = Decimal("0.01")
_HUNDRED = Decimal("100")


@dataclass(frozen=True)
class IndexBar:
    """지수 일봉 (포트 값 타입 — infra·application 공용)."""

    index: str
    day: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    provisional: bool = False


@dataclass(frozen=True)
class IndexPoint:
    day: date
    close: Decimal
    rate: Decimal
    """연초 첫 봉 종가 대비 %."""
    provisional: bool


def tail_range(
    last: date | None, year_start: date, today: date
) -> tuple[date, date] | None:
    """받아야 할 꼬리 구간. 오늘까지 저장돼 있으면 None."""
    if last is None or last < year_start:
        return (year_start, today)
    if last >= today:
        return None
    return (last + timedelta(days=1), today)


def split_ranges(
    start: date, end: date, days: int = CHUNK_DAYS
) -> list[tuple[date, date]]:
    """오래된 순, 각 구간 길이 ≤ days, 빈틈·겹침 없음."""
    chunks: list[tuple[date, date]] = []
    cursor = start
    step = timedelta(days=days - 1)
    while cursor <= end:
        chunk_end = min(cursor + step, end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def ytd_points(bars: list[IndexBar]) -> list[IndexPoint]:
    """날짜순 정렬·같은 날 중복은 확정 봉 우선. 기준 종가가 0 이하면 빈 목록."""
    by_day: dict[date, IndexBar] = {}
    for bar in bars:
        held = by_day.get(bar.day)
        if held is None or (held.provisional and not bar.provisional):
            by_day[bar.day] = bar
    ordered = [by_day[d] for d in sorted(by_day)]
    if not ordered or ordered[0].close <= 0:
        return []
    base = ordered[0].close
    return [
        IndexPoint(
            day=bar.day,
            close=bar.close,
            rate=((bar.close / base - 1) * _HUNDRED).quantize(
                _RATE_Q, rounding=ROUND_HALF_UP
            ),
            provisional=bar.provisional,
        )
        for bar in ordered
    ]
