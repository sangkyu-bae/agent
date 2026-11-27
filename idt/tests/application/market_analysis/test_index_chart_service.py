"""지수 YTD 차트 서비스 — 꼬리 적재 · 캐시 · 장중 봉 · 실패 상태.

Design Ref: market-index-ytd-chart §2.2, §6, §8.2 application. 네트워크·DB 없이.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

from src.application.market_analysis.index_chart import IndexChartService
from src.domain.market_analysis.index_chart import IndexBar
from src.domain.market_analysis.runtime import ToolOutcome, ToolSource
from src.domain.market_analysis.setting import MarketAnalysisSetting

from tests.application.market_analysis.fakes import FakeSettings

D = Decimal
TODAY = date(2026, 11, 27)  # 금요일
INTRADAY_UTC = datetime(2026, 11, 27, 2, 0)  # KST 11:00
AFTER_CLOSE_UTC = datetime(2026, 11, 27, 7, 0)  # KST 16:00
CONFIGURED = replace(
    MarketAnalysisSetting.defaults(), kis_server_id="kis-1", run_as_user_id="7"
)
BASE = {"KOSPI": D("2500"), "KOSDAQ": D("700")}


def _trading_days() -> list[date]:
    d, out = date(2026, 1, 2), []
    while d <= TODAY:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


DAYS = _trading_days()


def _close(index: str, day: date) -> D:
    return BASE[index] + DAYS.index(day)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class FakeKis:
    """get_index_history 흉내 — 범위 안 거래일 봉, 장중이면 오늘 봉은 provisional."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.calls: list[dict[str, Any]] = []
        self.fail_on: set[tuple[str, str]] = set()  # (index, start)
        self.fail_all = False
        self.truncated = False

    def _intraday(self) -> bool:
        return (self.clock.now + timedelta(hours=9)).hour < 16

    async def call(self, *, source, server_id, tool, args, run_as_user_id, request_id):
        assert source is ToolSource.KIS and tool == "get_index_history"
        assert server_id == "kis-1" and run_as_user_id == "7"
        self.calls.append(dict(args))
        if self.fail_all or (args["index"], args["start"]) in self.fail_on:
            return ToolOutcome(
                source=source,
                tool=tool,
                args=args,
                is_error=True,
                error_code="SERVER_UNAVAILABLE",
                text="SERVER_UNAVAILABLE",
            )
        start, end = date.fromisoformat(args["start"]), date.fromisoformat(args["end"])
        bars = [
            {
                "date": d.isoformat(),
                "open": str(_close(args["index"], d)),
                "high": str(_close(args["index"], d) + 5),
                "low": str(_close(args["index"], d) - 5),
                "close": str(_close(args["index"], d)),
                "volume": 1,
                "provisional": d == TODAY and self._intraday(),
            }
            for d in DAYS
            if start <= d <= end
        ][-args["limit"] :]
        payload = {
            "index": args["index"],
            "interval": "D",
            "bars": bars,
            "truncated": self.truncated,
        }
        return ToolOutcome(
            source=source,
            tool=tool,
            args=args,
            payload=payload,
            text=json.dumps(payload),
        )

    async def news(self, **kw):  # pragma: no cover — 쓰지 않음
        raise AssertionError


class FakeStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, date], IndexBar] = {}
        self.regime_rows: list[tuple[date, str]] = []
        self.fail_upsert = False

    async def last_date(self, index, since, request_id):
        days = [d for (i, d) in self.rows if i == index and d >= since]
        return max(days) if days else None

    async def upsert(self, bars, request_id):
        if self.fail_upsert:
            raise RuntimeError("db down")
        n = 0
        for b in bars:
            if not b.provisional:
                self.rows[(b.index, b.day)] = b
                n += 1
        return n

    async def bars(self, index, start, end, request_id):
        return sorted(
            (b for (i, d), b in self.rows.items() if i == index and start <= d <= end),
            key=lambda b: b.day,
        )

    async def regimes(self, start, end, request_id):
        return [(d, r) for d, r in self.regime_rows if start <= d <= end]


def _service(*, now=INTRADAY_UTC, setting=CONFIGURED):
    clock = Clock(now)
    kis, store, logger = FakeKis(clock), FakeStore(), MagicMock()
    svc = IndexChartService(
        settings=FakeSettings(setting),
        store=store,
        tools=kis,
        logger=logger,
        now_utc=clock,
    )
    return svc, kis, store, clock, logger


def _calls_by_index(kis: FakeKis) -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = {}
    for c in kis.calls:
        out.setdefault(c["index"], []).append((c["start"], c["end"]))
    return out


async def test_empty_table_backfills_in_two_chunks_per_index():
    # Plan SC-1 · FR-02 · FR-03
    svc, kis, store, _, _ = _service()
    res = await svc.chart("r")
    by_index = _calls_by_index(kis)
    assert by_index["KOSPI"] == [
        ("2026-01-01", "2026-07-02"),
        ("2026-07-03", "2026-11-27"),
    ]
    assert by_index["KOSDAQ"] == by_index["KOSPI"]
    assert all(c["limit"] == 200 and c["interval"] == "D" for c in kis.calls)
    # 확정 봉만 저장 — 장중 오늘 봉 제외 (SC-4)
    stored_days = sorted(d for (i, d) in store.rows if i == "KOSPI")
    assert stored_days == DAYS[:-1]
    kospi = res["series"]["KOSPI"]
    assert kospi["base_date"] == "2026-01-02"
    assert kospi["base_close"] == 2500.0
    assert len(kospi["points"]) == len(DAYS)
    assert kospi["points"][0] == {
        "date": "2026-01-02",
        "close": 2500.0,
        "rate": 0.0,
        "provisional": False,
    }
    last = kospi["points"][-1]
    assert last["date"] == "2026-11-27" and last["provisional"] is True
    assert all(not p["provisional"] for p in kospi["points"][:-1])
    assert res["source_status"] == "ok" and res["source_error"] is None
    assert res["year"] == 2026
    assert res["as_of"] == "2026-11-27T02:00:00Z"


async def test_rates_are_deterministic_from_closes():
    # Plan SC-3
    svc, *_ = _service()
    res = await svc.chart("r")
    p = res["series"]["KOSDAQ"]["points"][10]
    expected = (D(str(p["close"])) / D("700") - 1) * 100
    assert p["rate"] == float(expected.quantize(D("0.01")))


async def test_second_call_within_ttl_does_not_call_kis():
    # Plan SC-2 · FR-08
    svc, kis, _, clock, _ = _service()
    first = await svc.chart("r")
    n = len(kis.calls)
    clock.now += timedelta(minutes=4)
    second = await svc.chart("r")
    assert len(kis.calls) == n
    # 장중 봉은 캐시에서 그대로 붙는다
    assert (
        second["series"]["KOSPI"]["points"][-1]
        == first["series"]["KOSPI"]["points"][-1]
    )


async def test_after_ttl_fetches_only_today():
    svc, kis, _, clock, _ = _service()
    await svc.chart("r")
    kis.calls.clear()
    clock.now += timedelta(minutes=6)
    await svc.chart("r")
    assert _calls_by_index(kis) == {
        "KOSPI": [("2026-11-27", "2026-11-27")],
        "KOSDAQ": [("2026-11-27", "2026-11-27")],
    }


async def test_after_close_today_is_stored_and_no_more_calls():
    svc, kis, store, clock, _ = _service(now=AFTER_CLOSE_UTC)
    res = await svc.chart("r")
    assert ("KOSPI", TODAY) in store.rows
    assert res["series"]["KOSPI"]["points"][-1]["provisional"] is False
    kis.calls.clear()
    clock.now += timedelta(hours=1)
    await svc.chart("r")
    assert kis.calls == []


async def test_kis_failure_with_stored_data_is_stale():
    # Plan SC-5 · FR-07
    svc, kis, _, clock, _ = _service(now=AFTER_CLOSE_UTC)
    await svc.chart("r")
    clock.now += timedelta(days=3)  # 다음 주 월요일 → 꼬리 구간 필요
    kis.fail_all = True
    res = await svc.chart("r")
    assert res["source_status"] == "stale"
    assert res["source_error"] == "SERVER_UNAVAILABLE"
    assert len(res["series"]["KOSPI"]["points"]) == len(DAYS)


async def test_kis_failure_without_data_is_unavailable():
    svc, kis, _, _, _ = _service()
    kis.fail_all = True
    res = await svc.chart("r")
    assert res["source_status"] == "unavailable"
    assert res["series"]["KOSPI"] == {
        "base_date": None,
        "base_close": None,
        "points": [],
    }


async def test_failure_is_cached_within_ttl():
    svc, kis, _, clock, _ = _service()
    kis.fail_all = True
    await svc.chart("r")
    n = len(kis.calls)
    clock.now += timedelta(minutes=1)
    await svc.chart("r")
    assert len(kis.calls) == n


async def test_not_configured_does_not_call_kis():
    svc, kis, store, _, _ = _service(setting=MarketAnalysisSetting.defaults())
    res = await svc.chart("r")
    assert kis.calls == []
    assert res["source_status"] == "unavailable"
    assert res["source_error"] == "KIS_NOT_CONFIGURED"
    # 저장된 데이터가 있으면 stale
    store.rows[("KOSPI", date(2026, 1, 2))] = IndexBar(
        index="KOSPI", day=date(2026, 1, 2), open=D(1), high=D(1), low=D(1), close=D(1)
    )
    res = await svc.chart("r")
    assert res["source_status"] == "unavailable"  # KOSDAQ 은 여전히 없음 → 나쁜 쪽
    assert res["series"]["KOSPI"]["points"][0]["rate"] == 0.0


async def test_second_chunk_failure_keeps_first_chunk_and_resumes():
    svc, kis, store, clock, _ = _service()
    kis.fail_on = {("KOSPI", "2026-07-03")}
    res = await svc.chart("r")
    kospi_days = sorted(d for (i, d) in store.rows if i == "KOSPI")
    assert kospi_days[-1] <= date(2026, 7, 2) and kospi_days[0] == date(2026, 1, 2)
    assert res["source_status"] == "stale"
    kis.fail_on = set()
    kis.calls.clear()
    clock.now += timedelta(minutes=6)
    await svc.chart("r")
    assert _calls_by_index(kis)["KOSPI"] == [("2026-07-03", "2026-11-27")]


async def test_concurrent_requests_fetch_once():
    # Plan FR-09
    svc, kis, *_ = _service()
    a, b = await asyncio.gather(svc.chart("r1"), svc.chart("r2"))
    assert len(kis.calls) == 4
    assert a["series"] == b["series"]


async def test_regimes_are_included():
    # Plan SC-6 (데이터 측)
    svc, _, store, _, _ = _service()
    store.regime_rows = [
        (date(2025, 12, 30), "bull"),
        (date(2026, 11, 26), "strong_bear"),
    ]
    res = await svc.chart("r")
    assert res["regimes"] == [{"date": "2026-11-26", "value": "strong_bear"}]


async def test_truncated_response_logs_warning():
    svc, kis, _, _, logger = _service()
    kis.truncated = True
    await svc.chart("r")
    assert any("truncated" in str(c.args[0]) for c in logger.warning.call_args_list)


async def test_upsert_failure_is_stale_not_exception():
    svc, _, store, _, _ = _service()
    store.fail_upsert = True
    res = await svc.chart("r")
    assert res["source_status"] in {"stale", "unavailable"}
    assert res["source_error"] == "STORE_FAILED"


async def test_bad_bar_values_are_skipped():
    svc, kis, store, _, _ = _service()
    original = kis.call

    async def broken(**kw):
        out = await original(**kw)
        if isinstance(out.payload, dict) and out.payload["bars"]:
            out.payload["bars"][0]["close"] = "abc"
            out.payload["bars"][1]["close"] = "0"
        return out

    kis.call = broken  # type: ignore[method-assign]
    await svc.chart("r")
    assert ("KOSPI", date(2026, 1, 2)) not in store.rows
    assert ("KOSPI", date(2026, 1, 5)) not in store.rows
    assert ("KOSPI", date(2026, 1, 6)) in store.rows


async def test_setting_read_failure_is_status_not_exception():
    # gap G-M3 — 설정을 못 읽어도 500 이 아니라 저장분 + source_status
    svc, kis, store, _, _ = _service()

    class BrokenSettings:
        async def get(self, request_id):
            raise RuntimeError("db down")

    svc._settings = BrokenSettings()
    store.rows[("KOSPI", date(2026, 1, 2))] = IndexBar(
        index="KOSPI", day=date(2026, 1, 2), open=D(1), high=D(1), low=D(1), close=D(1)
    )
    res = await svc.chart("r")
    assert kis.calls == []
    assert res["source_error"] == "STORE_FAILED"
    assert res["series"]["KOSPI"]["points"][0]["rate"] == 0.0
