"""체제 계산 서비스 · 성과 스냅샷 (design §2.2 ①⑧, §6)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.market_analysis.performance import PerformanceRecorder
from src.application.market_analysis.regime import MarketRegimeService
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.value_objects import Regime

from .fakes import FakePositions, FakeRegimes, FakeTools

SETTING = MarketAnalysisSetting(kis_server_id="kis-1", run_as_user_id="7")
DAY = date(2026, 11, 26)


def _bars(n, last_close="110", step=0.5):
    bars = [
        {"date": f"2026-08-{(i % 28) + 1:02d}", "close": "100", "provisional": False}
        for i in range(n - 20)
    ]
    bars += [
        {
            "date": f"2026-11-{i + 1:02d}",
            "close": str(100 + step * (i + 1)),
            "provisional": False,
        }
        for i in range(20)
    ]
    bars[-1] = {"date": "2026-11-26", "close": last_close, "provisional": True}
    return bars


def _tools(kospi=None, kosdaq_close="900.5"):
    tools = FakeTools()

    def respond(args):
        if args["index"] == "KOSPI":
            return {"index": "KOSPI", "bars": kospi if kospi is not None else _bars(80)}
        return {
            "index": "KOSDAQ",
            "bars": [{"date": "2026-11-26", "close": kosdaq_close}],
        }

    tools.payloads["get_index_history"] = respond
    return tools


async def test_snapshot_strong_bull_context_and_save():
    tools = _tools()
    regimes = FakeRegimes()
    service = MarketRegimeService(tools=tools, regimes=regimes, logger=MagicMock())
    snap = await service.snapshot(SETTING, "r")
    assert snap.regime.regime is Regime.STRONG_BULL and snap.kospi_bars == 80
    assert snap.kospi_day == DAY and snap.kosdaq_close == Decimal("900.5")
    assert snap.context.startswith("[시장 체제] 강한 상승(strong_bull)")
    assert "KOSPI: 110 (2026-11-26 (미확정))" in snap.context
    limits = {c[2]["index"]: c[2]["limit"] for c in tools.calls}
    assert limits == {"KOSPI": 80, "KOSDAQ": 5}

    await service.save(trade_date=DAY, snapshot=snap, request_id="r")
    result, kosdaq, bars = regimes.regimes[DAY]
    assert (
        result.regime is Regime.STRONG_BULL
        and kosdaq == Decimal("900.5")
        and bars == 80
    )


async def test_snapshot_without_index_is_neutral_and_not_saved():
    tools = FakeTools()
    tools.fail.add("get_index_history")
    regimes = FakeRegimes()
    service = MarketRegimeService(tools=tools, regimes=regimes, logger=MagicMock())
    snap = await service.snapshot(SETTING, "r")
    assert snap.regime.regime is Regime.NEUTRAL and snap.regime.insufficient
    assert snap.kospi_day is None and "KOSPI: 데이터 없음" in snap.context
    await service.save(trade_date=DAY, snapshot=snap, request_id="r")
    assert regimes.regimes == {}


async def test_performance_snapshot():
    positions = FakePositions()
    a = positions.seed(symbol="000001")
    positions.rows[a].update(status="closed", profit_rate=Decimal("5"), holding_days=3)
    b = positions.seed(symbol="000002", slot_weight=Decimal("0.5"))
    positions.rows[b].update(status="closed", profit_rate=Decimal("-2"), holding_days=1)
    positions.seed(symbol="000003")
    regimes = FakeRegimes(first=(Decimal("100"), Decimal("1000")))
    service = MarketRegimeService(tools=_tools(), regimes=None, logger=MagicMock())
    snap = await service.snapshot(SETTING, "r")

    await PerformanceRecorder(
        positions=positions, regimes=regimes, logger=MagicMock()
    ).record(trade_date=DAY, snapshot=snap, setting=SETTING, request_id="r")
    s = regimes.snapshots[DAY]
    assert s["realized_cum_rate"] == Decimal("0.4000")  # (5 - 1) / 10
    assert (s["open_positions"], s["used_slots"]) == (1, Decimal("1"))
    assert s["kospi_cum_rate"] == Decimal("10.0000")
    assert s["kosdaq_cum_rate"] == Decimal("-9.9500")


async def test_performance_without_base_leaves_index_rates_empty():
    regimes = FakeRegimes()
    service = MarketRegimeService(tools=_tools(), regimes=None, logger=MagicMock())
    snap = await service.snapshot(SETTING, "r")
    await PerformanceRecorder(
        positions=FakePositions(), regimes=regimes, logger=MagicMock()
    ).record(trade_date=DAY, snapshot=snap, setting=SETTING, request_id="r")
    s = regimes.snapshots[DAY]
    assert s["kospi_cum_rate"] is None and s["realized_cum_rate"] == Decimal("0")
