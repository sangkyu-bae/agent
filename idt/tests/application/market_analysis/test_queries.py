"""조회 — 대시보드 KPI · 다음 회차 · 신호 규칙별 성과 · 페이지 자르기 (design §5.2)."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from unittest.mock import AsyncMock

from src.application.market_analysis.queries import MarketAnalysisQueries
from src.domain.market_analysis.setting import MarketAnalysisSetting

from .fakes import FakeSettings

NOW = datetime(2026, 11, 26, 1, 5)  # 목 서울 10:05
TRADES = [
    {
        "profit_rate": 5.0,
        "slot_weight": 1.0,
        "holding_days": 2,
        "rules": ["gap", "volume_spike"],
    },
    {"profit_rate": -2.0, "slot_weight": 1.0, "holding_days": 4, "rules": ["gap"]},
    {"profit_rate": 3.0, "slot_weight": 0.5, "holding_days": 6, "rules": []},
]


def _queries(setting=None, trades=TRADES):
    store = AsyncMock()
    store.closed_trades.return_value = trades
    store.open_summary.return_value = {"open_positions": 2, "used_slots": 2.0}
    store.equity_series.return_value = [{"date": "2026-11-25", "portfolio": 0.45}]
    store.latest_regime.return_value = {"date": "2026-11-26", "value": "bull"}
    store.last_round.return_value = None
    store.principles.return_value = [{"id": 1}]
    store.recent_journals.return_value = []
    store.list_positions.return_value = ([], 0)
    setting = setting or dataclasses.replace(
        MarketAnalysisSetting.defaults(), enabled=True
    )
    return MarketAnalysisQueries(
        store=store, settings=FakeSettings(setting), now_utc=lambda: NOW
    ), store


async def test_dashboard_kpi_next_round_and_parts():
    q, _ = _queries()
    d = await q.dashboard("r")
    assert d["as_of"] == "2026-11-26"
    assert d["switch"] == {"enabled": True, "next_round": "2026-11-26T05:00:00+00:00"}
    k = d["kpi"]
    assert (
        k["open_positions"],
        k["used_slots"],
        k["slot_count"],
        k["closed_trades"],
    ) == (2, 2.0, 10, 3)
    assert k["win_rate"] == 66.67 and k["realized_cum_rate"] == 0.45
    assert k["avg_holding_days"] == 4.0
    assert d["regime"]["value"] == "bull" and d["last_round"] is None
    assert d["equity"][0]["portfolio"] == 0.45


async def test_switch_off_has_no_next_round_and_empty_account_is_zero():
    q, _ = _queries(setting=MarketAnalysisSetting.defaults(), trades=[])
    d = await q.dashboard("r")
    assert d["switch"] == {"enabled": False, "next_round": None}
    assert d["kpi"]["closed_trades"] == 0 and d["kpi"]["win_rate"] == 0.0


async def test_rule_performance_counts_each_rule_per_trade():
    q, _ = _queries()
    rules = (await q.insights("r"))["rule_performance"]
    assert rules == [
        {"rule": "gap", "trades": 2, "win_rate": 50.0, "avg_profit_rate": 1.5},
        {
            "rule": "volume_spike",
            "trades": 1,
            "win_rate": 100.0,
            "avg_profit_rate": 5.0,
        },
    ]


async def test_page_size_is_clamped():
    q, store = _queries()
    page = await q.positions(status="open", page=0, size=1000, request_id="r")
    assert (page["page"], page["size"]) == (1, 100)
    assert store.list_positions.call_args.kwargs["size"] == 100


async def test_open_positions_get_current_price_and_unrealized_rate():
    from unittest.mock import MagicMock

    from .fakes import FakeTools

    store = AsyncMock()
    store.list_positions.return_value = (
        [
            {"symbol": "000660", "entry_price": 10000.0},
            {"symbol": "005930", "entry_price": 70000.0},
        ],
        2,
    )
    tools = FakeTools()
    tools.payloads["get_quotes"] = {"quotes": [{"symbol": "000660", "price": "10550"}]}
    setting = dataclasses.replace(
        MarketAnalysisSetting.defaults(), kis_server_id="kis-1", run_as_user_id="7"
    )
    q = MarketAnalysisQueries(
        store=store,
        settings=FakeSettings(setting),
        now_utc=lambda: NOW,
        tools=tools,
        logger=MagicMock(),
    )
    page = await q.positions(status="open", page=1, size=20, request_id="r")
    a, b = page["items"]
    assert (a["current_price"], a["unrealized_rate"]) == (10550.0, 5.5)
    assert (b["current_price"], b["unrealized_rate"]) == (None, None)  # 시세 없음 ≠ 0
    assert [c[2]["symbols"] for c in tools.calls] == [["000660", "005930"]]

    store.list_positions.return_value = ([{"symbol": "000660", "entry_price": 1.0}], 1)
    tools.calls.clear()
    await q.positions(status="closed", page=1, size=20, request_id="r")
    assert tools.calls == []  # 청산 목록은 시세를 부르지 않는다
