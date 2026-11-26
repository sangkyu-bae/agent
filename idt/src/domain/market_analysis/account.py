"""가상 계좌 결정론 정책 — 체제 · 진입 게이트 · 청산 · 성과.

Design Ref: stock-analysis-agents §6,
§1.1-2(판단은 재현 가능하게 — LLM 숫자는 입력일 뿐).
게이트의 가격은 판단 시점 시세(get_quote)다. 진입·청산 여부를 LLM 이 정하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Literal

from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.value_objects import Regime

_TWO = Decimal("0.01")
_FOUR = Decimal("0.0001")
_ZERO = Decimal("0")
_HUNDRED = Decimal("100")


def _q2(value: Decimal) -> Decimal:
    return value.quantize(_TWO, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    return value.quantize(_FOUR, rounding=ROUND_HALF_UP)


# ── 판단 출력 (에이전트 JSON 을 검증한 뒤의 값) ─────────────────────────────


@dataclass(frozen=True)
class BuyVerdict:
    score: int
    decision: Literal["enter", "skip"]
    target_price: Decimal | None
    stop_loss: Decimal | None
    investment_period: str | None
    sector: str | None
    rationale: str
    skip_reason: str | None


@dataclass(frozen=True)
class SellVerdict:
    action: Literal["hold", "sell", "adjust"]
    new_target_price: Decimal | None
    new_stop_loss: Decimal | None
    confidence: int
    reason: str


# ── 체제 ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RegimeResult:
    regime: Regime
    close: Decimal | None
    ma20: Decimal | None
    ma60: Decimal | None
    r20: Decimal | None
    insufficient: bool


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values, _ZERO) / Decimal(len(values))


class RegimePolicy:
    STRONG_PCT = Decimal("5")

    @staticmethod
    def decide(closes: list[Decimal]) -> RegimeResult:
        """KOSPI 종가(오래된 순). C·MA20·MA60·20일 수익률 R20 로 5단계 (Design §6)."""
        if len(closes) < 60:
            last = closes[-1] if closes else None
            return RegimeResult(Regime.NEUTRAL, last, None, None, None, True)
        c = closes[-1]
        ma20 = _mean(closes[-20:])
        ma60 = _mean(closes[-60:])
        r20 = (c / closes[-21] - 1) * _HUNDRED
        strong = RegimePolicy.STRONG_PCT
        if c > ma20 > ma60 and r20 >= strong:
            regime = Regime.STRONG_BULL
        elif c < ma20 < ma60 and r20 <= -strong:
            regime = Regime.STRONG_BEAR
        elif c > ma20 and ma20 >= ma60:
            regime = Regime.BULL
        elif c < ma20 and ma20 < ma60:
            regime = Regime.BEAR
        else:
            regime = Regime.NEUTRAL
        return RegimeResult(regime, c, _q2(ma20), _q2(ma60), _q2(r20), False)


# ── 진입 게이트 ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GateResult:
    passed: bool
    reasons: tuple[str, ...]
    price: Decimal
    rr: Decimal | None
    stop_pct: Decimal | None

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reasons": list(self.reasons),
            "price": str(self.price),
            "rr": None if self.rr is None else str(self.rr),
            "stop_pct": None if self.stop_pct is None else str(self.stop_pct),
        }


class EntryGatePolicy:
    @staticmethod
    def check(
        verdict: BuyVerdict,
        *,
        price: Decimal,
        regime: Regime,
        setting: MarketAnalysisSetting,
        open_positions: int,
        already_held: bool,
        provisional: bool,
    ) -> GateResult:
        """모든 조건을 검사해 사유를 쌓는다 — 하나라도 있으면 진입하지 않는다."""
        reasons: list[str] = []
        rr: Decimal | None = None
        stop_pct: Decimal | None = None
        if verdict.decision != "enter":
            reasons.append("DECISION_SKIP")
        minimum = setting.min_score_by_regime.get(regime.value, 10)
        if verdict.score < minimum:
            reasons.append(
                f"SCORE_BELOW_MIN({verdict.score}<{minimum}, {regime.value})"
            )
        target, stop = verdict.target_price, verdict.stop_loss
        if target is None or stop is None:
            reasons.append("PRICE_LEVELS_MISSING")
        elif not stop < price < target:
            reasons.append("LEVELS_INVALID")
        else:
            stop_pct = _q2((price - stop) / price * _HUNDRED)
            rr = _q2((target - price) / (price - stop))
            if stop_pct > setting.max_stop_pct:
                reasons.append(f"STOP_TOO_WIDE({stop_pct}>{_q2(setting.max_stop_pct)})")
            if stop_pct < setting.min_stop_pct:
                reasons.append(
                    f"STOP_TOO_TIGHT({stop_pct}<{_q2(setting.min_stop_pct)})"
                )
            if rr < setting.min_rr:
                reasons.append(f"RR_BELOW_MIN({rr}<{_q2(setting.min_rr)})")
        if open_positions >= setting.slot_count:
            reasons.append("NO_SLOT")
        if already_held:
            reasons.append("ALREADY_HELD")
        if provisional and not setting.intraday_entry_allowed:
            reasons.append("INTRADAY_ENTRY_OFF")
        return GateResult(not reasons, tuple(reasons), price, rr, stop_pct)


# ── 청산 ──────────────────────────────────────────────────────────────────


class ExitReason(StrEnum):
    TARGET = "target"
    STOP = "stop"
    JUDGE = "judge"


class ExitPolicy:
    @staticmethod
    def check(*, price: Decimal, stop: Decimal, target: Decimal) -> ExitReason | None:
        if price <= stop:
            return ExitReason.STOP
        if price >= target:
            return ExitReason.TARGET
        return None

    @staticmethod
    def valid_adjustment(verdict: SellVerdict, *, price: Decimal) -> bool:
        """adjust 는 새 손절 < 현재가 < 새 목표일 때만 반영한다 (§6)."""
        stop, target = verdict.new_stop_loss, verdict.new_target_price
        return stop is not None and target is not None and stop < price < target


# ── 성과 ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PerformanceSummary:
    closed: int
    wins: int
    win_rate: Decimal
    avg_profit_rate: Decimal
    avg_holding_days: Decimal
    realized_cum_rate: Decimal


class PerformancePolicy:
    @staticmethod
    def profit_rate(entry: Decimal, exit_price: Decimal) -> Decimal:
        return _q4((exit_price / entry - 1) * _HUNDRED)

    @staticmethod
    def holding_days(entry_at: datetime, exit_at: datetime) -> int:
        return (exit_at.date() - entry_at.date()).days

    @staticmethod
    def summary(
        closed: list[tuple[Decimal, Decimal]],
        *,
        slot_count: int,
        holding_days: list[int],
    ) -> PerformanceSummary:
        """closed = [(실현 수익률 %, 슬롯 비중)]. 실현 수익만 누적한다(복리 아님)."""
        if not closed:
            return PerformanceSummary(0, 0, _ZERO, _ZERO, _ZERO, _ZERO)
        wins = sum(1 for rate, _ in closed if rate > 0)
        cum = sum((rate * weight for rate, weight in closed), _ZERO) / Decimal(
            slot_count
        )
        avg = sum((rate for rate, _ in closed), _ZERO) / Decimal(len(closed))
        days = (
            (Decimal(sum(holding_days)) / Decimal(len(holding_days))).quantize(
                Decimal("0.1")
            )
            if holding_days
            else _ZERO
        )
        return PerformanceSummary(
            closed=len(closed),
            wins=wins,
            win_rate=_q2(Decimal(wins) / Decimal(len(closed)) * _HUNDRED),
            avg_profit_rate=_q4(avg),
            avg_holding_days=days,
            realized_cum_rate=_q4(cum),
        )


# ── 저장 값 (포트가 주고받는 타입) ──────────────────────────────────────────


@dataclass(frozen=True)
class Position:
    id: int
    symbol: str
    name: str | None
    sector: str | None
    slot_weight: Decimal
    entry_price: Decimal
    entry_at: datetime
    target_price: Decimal
    stop_loss: Decimal
    buy_decision_id: int | None = None
    buy_rationale: str | None = None


@dataclass(frozen=True)
class ClosedTrade:
    profit_rate: Decimal
    slot_weight: Decimal
    holding_days: int


@dataclass(frozen=True)
class DecisionDraft:
    """ma_decision 1행. 매수 보류(skip)는 관심종목으로 화면에 나온다."""

    kind: Literal["buy", "sell"]
    symbol: str
    name: str | None
    decision: str
    created_at: datetime
    report_id: int | None = None
    position_id: int | None = None
    score: int | None = None
    target_price: Decimal | None = None
    stop_loss: Decimal | None = None
    investment_period: str | None = None
    sector: str | None = None
    confidence: int | None = None
    rationale: str | None = None
    skip_reason: str | None = None
    gate: dict | None = None
    principles_used: tuple[int, ...] = ()
    price_at_decision: Decimal | None = None
    regime: str | None = None
    provisional: bool = False
    run_id: str | None = None


@dataclass(frozen=True)
class ActivePrinciple:
    id: int
    text: str
