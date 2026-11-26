"""보유 관리 — 결정론 청산(SC-4) · 매도 판단 hold/sell/adjust
· 저널 자리 (design §2.2 ②, U4)."""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.market_analysis.positions import PositionManager
from src.domain.market_analysis.account import ExitReason
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.value_objects import AgentRole

from .fakes import (
    FakeDecisions,
    FakeExtractor,
    FakePositions,
    FakeRoles,
    FakeRunner,
    FakeTools,
)

NOW = datetime(2026, 11, 26, 6, 30)  # 서울 15:30
SETTING = dataclasses.replace(
    MarketAnalysisSetting.defaults(), kis_server_id="kis-1", run_as_user_id="7"
)


def _sell(action="hold", target=None, stop=None, confidence=6):
    t = "null" if target is None else f'"{target}"'
    s = "null" if stop is None else f'"{stop}"'
    return (
        f'```json\n{{"action": "{action}", "new_target_price": {t}, '
        f'"new_stop_loss": {s}, "confidence": {confidence}, "reason": "근거"}}\n```'
    )


def _manager(prices, answer=_sell(), roles=None, on_closed=None, extractor=None):
    tools = FakeTools()
    tools.payloads["get_quotes"] = lambda args: {
        "quotes": [
            {"symbol": s, "price": prices[s]} for s in args["symbols"] if s in prices
        ],
        "missing": [s for s in args["symbols"] if s not in prices],
    }
    positions = FakePositions()
    decisions = FakeDecisions()
    runner = FakeRunner(answers={"sell_judge": answer})
    manager = PositionManager(
        tools=tools,
        runner=runner,
        roles=roles or FakeRoles(),
        positions=positions,
        decisions=decisions,
        extractor=extractor,
        principles=None,
        logger=MagicMock(),
        now_utc=lambda: NOW,
        on_closed=on_closed,
    )
    return manager, positions, decisions, runner, tools


async def _manage(manager, provisional=False):
    return await manager.manage(
        SETTING,
        regime="bull",
        provisional=provisional,
        run_slots=asyncio.Semaphore(4),
        request_id="r",
    )


async def test_sc4_stop_and_target_close_without_agent_and_notify_journal():
    closed_seen = []

    async def on_closed(pid, request_id):
        closed_seen.append(pid)

    manager, positions, decisions, runner, _ = _manager(
        {"000001": "9400", "000002": "12500"}, on_closed=on_closed
    )
    a = positions.seed(symbol="000001")
    b = positions.seed(symbol="000002")
    result = await _manage(manager)

    assert sorted(result.closed) == [a, b] and runner.runs == []
    ra, rb = positions.rows[a], positions.rows[b]
    assert (ra["status"], ra["exit_reason"], ra["exit_price"]) == (
        "closed",
        ExitReason.STOP,
        Decimal("9400"),
    )
    assert ra["profit_rate"] == Decimal("-6.0000") and ra["holding_days"] == 6
    assert rb["exit_reason"] is ExitReason.TARGET and rb["profit_rate"] == Decimal(
        "25.0000"
    )
    assert {d.decision for d in decisions.rows} == {"sell"}
    assert all("결정론 청산" in d.rationale for d in decisions.rows)
    assert sorted(closed_seen) == [a, b]


async def test_hold_records_decision_and_keeps_position():
    manager, positions, decisions, runner, tools = _manager({"000001": "10500"})
    pid = positions.seed(symbol="000001")
    result = await _manage(manager)
    assert result.closed == () and result.judged == 1 and result.tokens == 100
    assert positions.rows[pid]["status"] == "open"
    (d,) = decisions.rows
    assert (d.kind, d.decision, d.confidence, d.position_id) == ("sell", "hold", 6, pid)
    ctx = runner.runs[0]["reference_context"]
    assert (
        "[포지션]" in ctx
        and "진입 대비 5.0000%" in ctx
        and "[매수 당시 근거]\n매수 근거" in ctx
    )
    assert any(c[1] == "compute_indicators" for c in tools.calls)


async def test_sell_verdict_closes_with_judge_reason():
    manager, positions, decisions, _, _ = _manager(
        {"000001": "10200"}, answer=_sell("sell")
    )
    pid = positions.seed(symbol="000001")
    result = await _manage(manager)
    assert result.closed == (pid,)
    assert positions.rows[pid]["exit_reason"] is ExitReason.JUDGE
    assert decisions.rows[0].decision == "sell"


async def test_adjust_applies_only_when_levels_bracket_price():
    manager, positions, decisions, _, _ = _manager(
        {"000001": "10500"}, answer=_sell("adjust", target="13000", stop="10000")
    )
    pid = positions.seed(symbol="000001")
    result = await _manage(manager)
    assert result.adjusted == (pid,)
    assert positions.rows[pid]["stop_loss"] == Decimal("10000")

    manager, positions, decisions, _, _ = _manager(
        {"000001": "10500"}, answer=_sell("adjust", target="13000", stop="10600")
    )
    pid = positions.seed(symbol="000001")
    result = await _manage(manager)
    assert result.adjusted == () and positions.rows[pid]["stop_loss"] == Decimal("9500")
    assert decisions.rows[0].skip_reason.startswith("ADJUST_REJECTED")


async def test_parse_failure_holds():
    ex = FakeExtractor(None)
    manager, positions, decisions, _, _ = _manager(
        {"000001": "10500"}, answer="잘 모르겠다", extractor=ex
    )
    pid = positions.seed(symbol="000001")
    await _manage(manager)
    assert positions.rows[pid]["status"] == "open" and ex.calls == 1
    assert (decisions.rows[0].decision, decisions.rows[0].skip_reason) == (
        "hold",
        "PARSE_FAILED",
    )


async def test_missing_quote_leaves_position_untouched():
    manager, positions, decisions, runner, _ = _manager({})
    positions.seed(symbol="000001")
    result = await _manage(manager)
    assert result.unpriced == ("000001",) and decisions.rows == [] and runner.runs == []


async def test_role_unmapped_still_runs_deterministic_exit():
    roles = FakeRoles({r: r.value for r in AgentRole if r is not AgentRole.SELL_JUDGE})
    manager, positions, decisions, runner, _ = _manager(
        {"000001": "9000", "000002": "10500"}, roles=roles
    )
    a = positions.seed(symbol="000001")
    positions.seed(symbol="000002")
    result = await _manage(manager)
    assert result.closed == (a,) and runner.runs == []
    assert sorted(d.skip_reason or "" for d in decisions.rows) == ["", "ROLE_UNMAPPED"]


async def test_on_closed_failure_is_contained():
    async def boom(pid, request_id):
        raise RuntimeError("journal down")

    manager, positions, _, _, _ = _manager({"000001": "9000"}, on_closed=boom)
    pid = positions.seed(symbol="000001")
    result = await _manage(manager)
    assert result.closed == (pid,) and positions.rows[pid]["status"] == "closed"


async def test_no_positions_does_nothing():
    manager, _, _, runner, tools = _manager({})
    result = await _manage(manager)
    assert result.closed == () and tools.calls == [] and runner.runs == []


async def test_m4_one_position_exception_does_not_drop_other_closures():
    """중간 점검 M4: 한 포지션의 예외가 다른 청산의 저널(on_closed)을 빼먹지 않는다."""
    closed_seen = []

    async def on_closed(pid, request_id):
        closed_seen.append(pid)

    manager, positions, _, _, tools = _manager(
        {"000001": "9000", "000002": "10500"}, on_closed=on_closed
    )
    a = positions.seed(symbol="000001")
    b = positions.seed(symbol="000002")
    original = tools.call

    async def flaky(**kw):
        if kw["tool"] == "compute_indicators":
            raise RuntimeError("indicator crash")
        return await original(**kw)

    tools.call = flaky
    result = await _manage(manager)
    assert result.closed == (a,) and closed_seen == [a]
    assert result.errors == (b,) and positions.rows[b]["status"] == "open"
