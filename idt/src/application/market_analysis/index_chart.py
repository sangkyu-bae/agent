"""지수 YTD 차트 — 꼬리 적재 + 조회 조립 (`GET /market-analysis/index-chart`).

Design Ref: market-index-ytd-chart §2.2, §4.2, §6
- 지수별로 마지막 저장일 다음 날 ~ 오늘만 KIS get_index_history 로
  받는다 (Plan FR-02). 183일 구간으로 나눠 오래된 구간부터 부르고,
  실패하면 거기서 멈춘다(앞 구간 저장분 유지).
- 확정 봉만 저장하고 장중 봉은 메모리 캐시에만 둔다 (Plan FR-04).
- 캐시 TTL 안의 재조회는 KIS 를 부르지 않는다 (Plan SC-2).
  실패 결과도 TTL 동안 캐시한다.
- 적재 단계는 asyncio.Lock 으로 직렬화 — 동시 조회가 같은 구간을
  두 번 받지 않는다 (Plan FR-09).
- 실패는 예외가 아니라 source_status(ok·stale·unavailable)로 (Plan FR-07).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from src.application.market_analysis.ports import (
    IndexDailyStore,
    MarketTools,
    SettingReader,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.index_chart import (
    FETCH_LIMIT,
    INDEXES,
    IndexBar,
    IndexPoint,
    split_ranges,
    tail_range,
    ytd_points,
)
from src.domain.market_analysis.round import RoundSchedulePolicy
from src.domain.market_analysis.runtime import ToolSource
from src.domain.market_analysis.setting import MarketAnalysisSetting

CACHE_TTL_SEC = 300
NOT_CONFIGURED = "KIS_NOT_CONFIGURED"
STORE_FAILED = "STORE_FAILED"
_STATUS_RANK = {"ok": 0, "stale": 1, "unavailable": 2}


@dataclass(frozen=True)
class _Fetched:
    at: datetime
    provisional: IndexBar | None
    error: str | None


def _num(value: Any) -> Decimal | None:
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return n if n.is_finite() and n > 0 else None


def _parse_bars(
    index: str, payload: dict[str, Any], start: date, end: date
) -> list[IndexBar]:
    """값이 이상한 봉은 버린다 (Design §6)."""
    out: list[IndexBar] = []
    for raw in payload.get("bars") or []:
        if not isinstance(raw, dict):
            continue
        try:
            day = date.fromisoformat(str(raw.get("date")))
        except ValueError:
            continue
        prices = [_num(raw.get(k)) for k in ("open", "high", "low", "close")]
        if not start <= day <= end or any(p is None for p in prices):
            continue
        o, h, lo, c = prices
        out.append(
            IndexBar(
                index=index,
                day=day,
                open=o,
                high=h,
                low=lo,
                close=c,  # type: ignore[arg-type]
                provisional=bool(raw.get("provisional")),
            )
        )
    return out


def _point(p: IndexPoint) -> dict[str, Any]:
    return {
        "date": p.day.isoformat(),
        "close": float(p.close),
        "rate": float(p.rate),
        "provisional": p.provisional,
    }


class IndexChartService:
    def __init__(
        self,
        *,
        settings: SettingReader,
        store: IndexDailyStore,
        tools: MarketTools,
        logger: LoggerInterface,
        now_utc: Callable[[], datetime],
        cache_ttl_sec: int = CACHE_TTL_SEC,
    ) -> None:
        self._settings = settings
        self._store = store
        self._tools = tools
        self._logger = logger
        self._now_utc = now_utc
        self._ttl = timedelta(seconds=cache_ttl_sec)
        self._fetched: dict[str, _Fetched] = {}
        self._lock = asyncio.Lock()

    async def chart(self, request_id: str) -> dict[str, Any]:
        now = self._now_utc()
        today = RoundSchedulePolicy.to_kst(now).date()
        year_start = date(today.year, 1, 1)
        errors: dict[str, str | None] = {}
        try:
            setting = await self._settings.get(request_id)
        except Exception as e:  # noqa: BLE001 — gap G-M3: 저장분으로 응답한다
            self._logger.warning(
                "market_analysis setting read failed",
                exception=e,
                request_id=request_id,
            )
            errors = dict.fromkeys(INDEXES, STORE_FAILED)
        else:
            async with self._lock:
                for index in INDEXES:
                    errors[index] = await self._refresh(
                        index, setting, now, year_start, today, request_id
                    )

        series: dict[str, Any] = {}
        status, first_error = "ok", None
        for index in INDEXES:
            points, read_error = await self._points(
                index, year_start, today, request_id
            )
            error = errors[index] or read_error
            index_status = (
                "ok" if error is None else ("stale" if points else "unavailable")
            )
            if _STATUS_RANK[index_status] > _STATUS_RANK[status]:
                status = index_status
            if error is not None and first_error is None:
                first_error = error
            series[index] = {
                "base_date": points[0].day.isoformat() if points else None,
                "base_close": float(points[0].close) if points else None,
                "points": [_point(p) for p in points],
            }
        return {
            "year": today.year,
            "series": series,
            "regimes": await self._regimes(year_start, today, request_id),
            "source_status": status,
            "source_error": first_error,
            "as_of": now.replace(microsecond=0).isoformat() + "Z",
        }

    async def _refresh(
        self,
        index: str,
        setting: MarketAnalysisSetting,
        now: datetime,
        year_start: date,
        today: date,
        request_id: str,
    ) -> str | None:
        cached = self._fetched.get(index)
        if cached is not None and now - cached.at < self._ttl:
            return cached.error
        if not setting.kis_server_id or not setting.run_as_user_id:
            return NOT_CONFIGURED
        try:
            last = await self._store.last_date(index, year_start, request_id)
        except Exception as e:  # noqa: BLE001 — 조회는 저장분으로 계속한다
            self._logger.warning(
                "market_analysis index store read failed",
                exception=e,
                request_id=request_id,
                index=index,
            )
            return STORE_FAILED
        provisional: IndexBar | None = None
        error: str | None = None
        rng = tail_range(last, year_start, today)
        for start, end in split_ranges(*rng) if rng else []:
            outcome = await self._tools.call(
                source=ToolSource.KIS,
                server_id=setting.kis_server_id,
                tool="get_index_history",
                args={
                    "index": index,
                    "interval": "D",
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "limit": FETCH_LIMIT,
                },
                run_as_user_id=setting.run_as_user_id,
                request_id=request_id,
            )
            if outcome.is_error or not isinstance(outcome.payload, dict):
                error = outcome.error_code or "TOOL_CALL_FAILED"
                self._logger.warning(
                    "market_analysis index history unavailable",
                    request_id=request_id,
                    index=index,
                    error_code=error,
                    start=start.isoformat(),
                    end=end.isoformat(),
                )
                break
            if outcome.payload.get("truncated"):
                self._logger.warning(
                    "market_analysis index history truncated",
                    request_id=request_id,
                    index=index,
                    start=start.isoformat(),
                    end=end.isoformat(),
                )
            bars = _parse_bars(index, outcome.payload, start, end)
            try:
                await self._store.upsert(bars, request_id)
            except Exception as e:  # noqa: BLE001
                self._logger.warning(
                    "market_analysis index store write failed",
                    exception=e,
                    request_id=request_id,
                    index=index,
                )
                error = STORE_FAILED
                break
            live = [b for b in bars if b.provisional and b.day == today]
            if live:
                provisional = live[-1]
        self._fetched[index] = _Fetched(at=now, provisional=provisional, error=error)
        return error

    async def _points(
        self, index: str, year_start: date, today: date, request_id: str
    ) -> tuple[list[IndexPoint], str | None]:
        try:
            bars = await self._store.bars(index, year_start, today, request_id)
        except Exception as e:  # noqa: BLE001
            self._logger.warning(
                "market_analysis index store read failed",
                exception=e,
                request_id=request_id,
                index=index,
            )
            bars, read_error = [], STORE_FAILED
        else:
            read_error = None
        cached = self._fetched.get(index)
        if cached is not None and cached.provisional is not None:
            if cached.provisional.day == today:
                bars = [*bars, cached.provisional]
        return ytd_points(bars), read_error

    async def _regimes(
        self, year_start: date, today: date, request_id: str
    ) -> list[dict[str, str]]:
        try:
            rows = await self._store.regimes(year_start, today, request_id)
        except Exception as e:  # noqa: BLE001
            self._logger.warning(
                "market_analysis regime read failed", exception=e, request_id=request_id
            )
            return []
        return [{"date": d.isoformat(), "value": r} for d, r in rows]
