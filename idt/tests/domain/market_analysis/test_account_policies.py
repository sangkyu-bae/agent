"""가상 계좌 결정론 정책 — 체제 · 진입 게이트 · 청산 · 성과 (design §6, U1~U5)."""

from __future__ import annotations

import dataclasses
from datetime import datetime
from decimal import Decimal

import pytest
from src.domain.market_analysis.account import (
    BuyVerdict,
    EntryGatePolicy,
    ExitPolicy,
    ExitReason,
    PerformancePolicy,
    RegimePolicy,
    SellVerdict,
)
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.value_objects import Regime

D = Decimal
SETTING = MarketAnalysisSetting.defaults()


# ── 체제 (U5) ──────────────────────────────────────────────────────────────


def _closes(base: float, last20_step: float, n: int = 80) -> list[Decimal]:
    """n 개 종가 — 앞부분은 base 근처, 마지막 20봉은 step 씩 변한다."""
    values = [D(str(base))] * (n - 20)
    values += [D(str(base + last20_step * (i + 1))) for i in range(20)]
    return values


def test_regime_insufficient_bars_is_neutral():
    result = RegimePolicy.decide([D("100")] * 59)
    assert result.regime is Regime.NEUTRAL and result.insufficient is True


def test_regime_strong_bull_and_strong_bear():
    up = RegimePolicy.decide(_closes(100, 0.5))  # +10% in 20 bars, C > MA20 > MA60
    assert up.regime is Regime.STRONG_BULL and up.r20 is not None and up.r20 >= D("5")
    down = RegimePolicy.decide(_closes(100, -0.5))
    assert down.regime is Regime.STRONG_BEAR


def test_regime_bull_bear_neutral():
    assert RegimePolicy.decide(_closes(100, 0.1)).regime is Regime.BULL  # +2%
    assert RegimePolicy.decide(_closes(100, -0.1)).regime is Regime.BEAR
    flat = [D("100")] * 80
    assert RegimePolicy.decide(flat).regime is Regime.NEUTRAL


# ── 진입 게이트 (U1~U3) ─────────────────────────────────────────────────────


def _buy(**kw) -> BuyVerdict:
    base = dict(
        score=8,
        decision="enter",
        target_price=D("10800"),
        stop_loss=D("9500"),
        investment_period="단기",
        sector="반도체",
        rationale="근거",
        skip_reason=None,
    )
    base.update(kw)
    return BuyVerdict(**base)


def _gate(
    verdict,
    price=D("10000"),
    regime=Regime.BULL,
    open_count=0,
    held=False,
    provisional=False,
    setting=SETTING,
):
    return EntryGatePolicy.check(
        verdict,
        price=price,
        regime=regime,
        setting=setting,
        open_positions=open_count,
        already_held=held,
        provisional=provisional,
    )


def test_gate_passes_when_everything_fits():
    r = _gate(_buy(target_price=D("12000")))  # stop 5%, RR 4.0
    assert r.passed and r.reasons == ()
    assert r.rr == D("4.00") and r.stop_pct == D("5.00")


def test_u1_score_below_regime_minimum():
    r = _gate(_buy(score=6, target_price=D("12000")), regime=Regime.BEAR)
    assert not r.passed and "SCORE_BELOW_MIN(6<7, bear)" in r.reasons


def test_u2_rr_below_minimum():
    r = _gate(_buy())  # stop 5%, RR (10800-10000)/(10000-9500)=1.6
    assert not r.passed and "RR_BELOW_MIN(1.60<2.00)" in r.reasons


def test_u3_no_slot():
    r = _gate(_buy(target_price=D("12000")), open_count=10)
    assert not r.passed and "NO_SLOT" in r.reasons


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"decision": "skip"}, "DECISION_SKIP"),
        ({"target_price": None}, "PRICE_LEVELS_MISSING"),
        ({"stop_loss": D("10100")}, "LEVELS_INVALID"),
        (
            {"stop_loss": D("9000"), "target_price": D("13000")},
            "STOP_TOO_WIDE(10.00>7.00)",
        ),
        (
            {"stop_loss": D("9950"), "target_price": D("12000")},
            "STOP_TOO_TIGHT(0.50<2.00)",
        ),
    ],
)
def test_gate_reasons(kwargs, reason):
    r = _gate(_buy(**kwargs))
    assert not r.passed and reason in r.reasons


def test_gate_collects_every_reason_and_blocks_held_and_intraday_off():
    setting = dataclasses.replace(SETTING, intraday_entry_allowed=False)
    r = _gate(
        _buy(score=1, target_price=D("12000")),
        held=True,
        provisional=True,
        setting=setting,
        open_count=10,
    )
    assert {"ALREADY_HELD", "INTRADAY_ENTRY_OFF", "NO_SLOT"} <= set(r.reasons)
    assert any(x.startswith("SCORE_BELOW_MIN") for x in r.reasons)


# ── 청산 (U4) ──────────────────────────────────────────────────────────────


def test_exit_policy():
    assert (
        ExitPolicy.check(price=D("9500"), stop=D("9500"), target=D("12000"))
        is ExitReason.STOP
    )
    assert (
        ExitPolicy.check(price=D("12100"), stop=D("9500"), target=D("12000"))
        is ExitReason.TARGET
    )
    assert ExitPolicy.check(price=D("10000"), stop=D("9500"), target=D("12000")) is None


def test_adjust_only_when_new_levels_bracket_price():
    ok = SellVerdict(
        action="adjust",
        new_target_price=D("13000"),
        new_stop_loss=D("9800"),
        confidence=6,
        reason="r",
    )
    assert ExitPolicy.valid_adjustment(ok, price=D("10000")) is True
    bad = dataclasses.replace(ok, new_stop_loss=D("10100"))
    assert ExitPolicy.valid_adjustment(bad, price=D("10000")) is False
    missing = dataclasses.replace(ok, new_target_price=None)
    assert ExitPolicy.valid_adjustment(missing, price=D("10000")) is False


def test_profit_rate_and_holding_days():
    assert PerformancePolicy.profit_rate(D("10000"), D("10550")) == D("5.5000")
    assert PerformancePolicy.profit_rate(D("10000"), D("9500")) == D("-5.0000")
    assert (
        PerformancePolicy.holding_days(
            datetime(2026, 11, 20, 1), datetime(2026, 11, 26, 9)
        )
        == 6
    )


def test_performance_summary():
    closed = [(D("5.0"), D("1")), (D("-2.0"), D("1")), (D("3.0"), D("0.5"))]
    s = PerformancePolicy.summary(closed, slot_count=10, holding_days=[2, 4, 6])
    assert s.closed == 3 and s.wins == 2
    assert s.win_rate == D("66.67")
    assert s.realized_cum_rate == D("0.4500")  # (5 - 2 + 1.5) / 10
    assert s.avg_profit_rate == D("2.0000") and s.avg_holding_days == D("4.0")
    empty = PerformancePolicy.summary([], slot_count=10, holding_days=[])
    assert (empty.closed, empty.win_rate, empty.realized_cum_rate) == (
        0,
        D("0"),
        D("0"),
    )
