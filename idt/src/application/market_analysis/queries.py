"""조회 — 대시보드 · 인사이트 계산과 목록·상세 위임 (module-8, view 권한).

Design Ref: stock-analysis-agents §5.1 · §5.2 GET /dashboard, §6 PerformancePolicy.
- KPI 는 청산 건으로만 계산한다(실현 수익). 보유 목록만 현재가·평가 수익률을 붙인다
- 신호 규칙별 성과 = 청산 건의 진입 근거
리포트에 있던 규칙마다 거래 수·승률·평균 수익률.
  한 거래에 규칙이 여럿이면 규칙마다 센다
- 다음 회차 = 설정 시각 중 다음 평일 시각(휴장일은 모른다)
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from src.application.market_analysis.ports import MarketTools, QueryStore, SettingReader
from src.application.market_analysis.quotes import fetch_quotes
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.market_analysis.account import PerformancePolicy
from src.domain.market_analysis.round import RoundSchedulePolicy

PAGE_MAX = 100
EQUITY_POINTS = 250
RECENT_JOURNALS = 10


def _f(value: Decimal) -> float:
    return float(value)


def clamp_page(page: int, size: int) -> tuple[int, int]:
    return max(1, page), min(max(1, size), PAGE_MAX)


def _iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.replace(tzinfo=UTC).isoformat()


class MarketAnalysisQueries:
    def __init__(
        self,
        *,
        store: QueryStore,
        settings: SettingReader,
        now_utc: Callable[[], datetime],
        tools: MarketTools | None = None,
        logger: LoggerInterface | None = None,
    ) -> None:
        self._store = store
        self._settings = settings
        self._now_utc = now_utc
        self._tools = tools
        self._logger = logger

    async def dashboard(self, request_id: str) -> dict[str, Any]:
        setting = await self._settings.get(request_id)
        trades = await self._store.closed_trades(request_id)
        summary = PerformancePolicy.summary(
            [
                (Decimal(str(t["profit_rate"])), Decimal(str(t["slot_weight"])))
                for t in trades
            ],
            slot_count=setting.slot_count,
            holding_days=[int(t["holding_days"]) for t in trades],
        )
        held = await self._store.open_summary(request_id)
        now = self._now_utc()
        return {
            "as_of": RoundSchedulePolicy.to_kst(now).date().isoformat(),
            "switch": {
                "enabled": setting.enabled,
                "next_round": _iso(
                    RoundSchedulePolicy.next_slot(now, setting.round_times)
                )
                if setting.enabled
                else None,
            },
            "kpi": {
                "open_positions": held["open_positions"],
                "used_slots": held["used_slots"],
                "slot_count": setting.slot_count,
                "closed_trades": summary.closed,
                "win_rate": _f(summary.win_rate),
                "avg_profit_rate": _f(summary.avg_profit_rate),
                "avg_holding_days": _f(summary.avg_holding_days),
                "realized_cum_rate": _f(summary.realized_cum_rate),
            },
            "equity": await self._store.equity_series(EQUITY_POINTS, request_id),
            "regime": await self._store.latest_regime(request_id),
            "last_round": await self._store.last_round(request_id),
        }

    async def insights(self, request_id: str) -> dict[str, Any]:
        trades = await self._store.closed_trades(request_id)
        by_rule: dict[str, list[Decimal]] = {}
        for t in trades:
            for rule in sorted(set(t.get("rules") or [])):
                by_rule.setdefault(rule, []).append(Decimal(str(t["profit_rate"])))
        rules = [
            {
                "rule": rule,
                "trades": len(rates),
                "win_rate": _f(
                    (
                        Decimal(sum(1 for r in rates if r > 0)) / len(rates) * 100
                    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                ),
                "avg_profit_rate": _f(
                    (sum(rates, Decimal("0")) / len(rates)).quantize(
                        Decimal("0.0001"), rounding=ROUND_HALF_UP
                    )
                ),
            }
            for rule, rates in sorted(
                by_rule.items(), key=lambda kv: (-len(kv[1]), kv[0])
            )
        ]
        return {
            "principles": await self._store.principles(request_id),
            "journals": await self._store.recent_journals(RECENT_JOURNALS, request_id),
            "rule_performance": rules,
        }

    # ── 목록·상세 — 저장소에 그대로 위임 (페이지 크기만 자른다) ──────────────

    async def positions(
        self, *, status: str, page: int, size: int, request_id: str
    ) -> dict[str, Any]:
        page, size = clamp_page(page, size)
        items, total = await self._store.list_positions(
            status=status, page=page, size=size, request_id=request_id
        )
        if status == "open" and items:
            items = await self._with_quotes(items, request_id)
        return {"items": items, "total": total, "page": page, "size": size}

    async def _with_quotes(
        self, items: list[dict[str, Any]], request_id: str
    ) -> list[dict[str, Any]]:
        """보유 표 현재가·평가 수익률 (module-9 결정).
        시세가 없으면 null — 0 이 아니다."""
        prices: dict[str, Decimal] = {}
        if self._tools is not None and self._logger is not None:
            setting = await self._settings.get(request_id)
            prices = await fetch_quotes(
                self._tools,
                setting,
                [str(i["symbol"]) for i in items],
                logger=self._logger,
                request_id=request_id,
            )
        out = []
        for item in items:
            price = prices.get(str(item["symbol"]))
            entry = item.get("entry_price")
            rate = (
                _f(PerformancePolicy.profit_rate(Decimal(str(entry)), price))
                if price is not None and entry
                else None
            )
            out.append(
                {
                    **item,
                    "current_price": None if price is None else _f(price),
                    "unrealized_rate": rate,
                }
            )
        return out

    async def position(
        self, position_id: int, request_id: str
    ) -> dict[str, Any] | None:
        return await self._store.position_detail(position_id, request_id)

    async def decisions(
        self, *, kind: str, decision: str | None, page: int, size: int, request_id: str
    ) -> dict[str, Any]:
        page, size = clamp_page(page, size)
        items, total = await self._store.list_decisions(
            kind=kind, decision=decision, page=page, size=size, request_id=request_id
        )
        return {"items": items, "total": total, "page": page, "size": size}

    async def reports(
        self,
        *,
        symbol: str | None,
        trade_date: Any,
        page: int,
        size: int,
        request_id: str,
    ) -> dict[str, Any]:
        page, size = clamp_page(page, size)
        items, total = await self._store.list_reports(
            symbol=symbol,
            trade_date=trade_date,
            page=page,
            size=size,
            request_id=request_id,
        )
        return {"items": items, "total": total, "page": page, "size": size}

    async def report(self, report_id: int, request_id: str) -> dict[str, Any] | None:
        return await self._store.report_detail(report_id, request_id)

    async def rounds(self, *, page: int, size: int, request_id: str) -> dict[str, Any]:
        page, size = clamp_page(page, size)
        items, total = await self._store.list_rounds(
            page=page, size=size, request_id=request_id
        )
        return {"items": items, "total": total, "page": page, "size": size}

    async def round(self, round_id: int, request_id: str) -> dict[str, Any] | None:
        return await self._store.round_detail(round_id, request_id)
