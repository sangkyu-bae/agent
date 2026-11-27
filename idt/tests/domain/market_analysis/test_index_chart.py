"""지수 YTD 차트 순수 규칙 — 꼬리 범위 · 구간 나누기 · 연초 대비 등락률.

Design Ref: market-index-ytd-chart §3.1, §8.2 domain.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from src.domain.market_analysis.index_chart import (
    CHUNK_DAYS,
    IndexBar,
    split_ranges,
    tail_range,
    ytd_points,
)

D = Decimal
Y0 = date(2026, 1, 1)
TODAY = date(2026, 11, 27)


def _bar(day: date, close: str, *, provisional: bool = False) -> IndexBar:
    c = D(close)
    return IndexBar(
        index="KOSPI",
        day=day,
        open=c,
        high=c,
        low=c,
        close=c,
        provisional=provisional,
    )


# ── tail_range ──────────────────────────────────────────────────────────


def test_tail_range_empty_table_starts_at_year_start():
    assert tail_range(None, Y0, TODAY) == (Y0, TODAY)


def test_tail_range_continues_after_last_stored_day():
    assert tail_range(date(2026, 11, 26), Y0, TODAY) == (TODAY, TODAY)


def test_tail_range_none_when_today_already_stored():
    assert tail_range(TODAY, Y0, TODAY) is None


def test_tail_range_ignores_last_day_before_year_start():
    # 작년 봉만 있으면 올해 1월 1일부터
    assert tail_range(date(2025, 12, 30), Y0, TODAY) == (Y0, TODAY)


# ── split_ranges ────────────────────────────────────────────────────────


def test_split_ranges_ytd_is_two_chunks_without_gap_or_overlap():
    chunks = split_ranges(Y0, TODAY)
    assert len(chunks) == 2
    assert chunks[0][0] == Y0
    assert chunks[-1][1] == TODAY
    assert chunks[1][0] == chunks[0][1] + timedelta(days=1)
    for start, end in chunks:
        assert (end - start).days + 1 <= CHUNK_DAYS


def test_split_ranges_single_day():
    assert split_ranges(TODAY, TODAY) == [(TODAY, TODAY)]


def test_split_ranges_custom_size():
    chunks = split_ranges(date(2026, 1, 1), date(2026, 1, 10), days=4)
    assert chunks == [
        (date(2026, 1, 1), date(2026, 1, 4)),
        (date(2026, 1, 5), date(2026, 1, 8)),
        (date(2026, 1, 9), date(2026, 1, 10)),
    ]


def test_split_ranges_reversed_is_empty():
    assert split_ranges(TODAY, Y0) == []


# ── ytd_points ──────────────────────────────────────────────────────────


def test_ytd_points_first_point_is_zero_and_rates_match():
    # Plan SC-3
    pts = ytd_points(
        [
            _bar(date(2026, 1, 5), "2600"),
            _bar(date(2026, 1, 2), "2500"),
            _bar(date(2026, 1, 6), "2400.5"),
        ]
    )
    assert [p.day for p in pts] == [
        date(2026, 1, 2),
        date(2026, 1, 5),
        date(2026, 1, 6),
    ]
    assert pts[0].rate == D("0.00")
    assert pts[1].rate == D("4.00")
    # (2400.5 / 2500 - 1) * 100 = -3.98
    assert pts[2].rate == D("-3.98")


def test_ytd_points_rounds_half_up():
    pts = ytd_points(
        [_bar(date(2026, 1, 2), "1000"), _bar(date(2026, 1, 5), "1000.125")]
    )
    # 0.0125% → 0.01
    assert pts[1].rate == D("0.01")
    pts = ytd_points(
        [_bar(date(2026, 1, 2), "1000"), _bar(date(2026, 1, 5), "1000.05")]
    )
    # 0.005% → 0.01 (ROUND_HALF_UP)
    assert pts[1].rate == D("0.01")


def test_ytd_points_same_day_prefers_confirmed_bar():
    pts = ytd_points(
        [
            _bar(date(2026, 1, 2), "2500"),
            _bar(date(2026, 1, 5), "2700", provisional=True),
            _bar(date(2026, 1, 5), "2600"),
        ]
    )
    assert len(pts) == 2
    assert pts[1].close == D("2600")
    assert pts[1].provisional is False


def test_ytd_points_keeps_provisional_flag():
    pts = ytd_points(
        [
            _bar(date(2026, 1, 2), "2500"),
            _bar(date(2026, 1, 5), "2550", provisional=True),
        ]
    )
    assert pts[-1].provisional is True
    assert pts[-1].rate == D("2.00")


def test_ytd_points_empty_or_bad_base():
    assert ytd_points([]) == []
    assert ytd_points([_bar(date(2026, 1, 2), "0"), _bar(date(2026, 1, 5), "10")]) == []
