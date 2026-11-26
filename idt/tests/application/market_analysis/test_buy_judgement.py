"""매수 판단 — 에이전트 점수 + 결정론 게이트 → 진입
또는 관심종목 (design §2.2 ⑥, §6, U9)."""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.market_analysis.judgement import BuyJudgement
from src.application.market_analysis.pipeline import PipelineResult
from src.domain.market_analysis.account import ActivePrinciple
from src.domain.market_analysis.report import AnalysisTarget, HeaderFacts, ReportStatus
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.value_objects import AgentRole

from .fakes import (
    FakeDecisions,
    FakeExtractor,
    FakePositions,
    FakePrinciples,
    FakeRoles,
    FakeRunner,
    FakeTools,
)

NOW = datetime(2026, 11, 26, 1, 10)
SETTING = dataclasses.replace(
    MarketAnalysisSetting.defaults(), kis_server_id="kis-1", run_as_user_id="7"
)
ENTER = (
    '```json\n{"score": 8, "decision": "enter", "target_price": 12000, '
    '"stop_loss": 9500, "investment_period": "단기", "sector": "반도체", '
    '"rationale": "수급 개선", "skip_reason": null}\n```'
)


def _target(symbol="000660", regime="bull", provisional=False):
    return AnalysisTarget(
        symbol=symbol,
        name=f"종목{symbol}",
        trade_date=date(2026, 11, 26),
        signals=({"rule": "gap"},),
        provisional=provisional,
        market_context="[시장 체제] 상승(bull)",
        round_id=1,
        regime=regime,
    )


def _result(strategy="시나리오", summary="요약"):
    header = HeaderFacts(
        symbol="000660",
        name="종목000660",
        trade_date=date(2026, 11, 26),
        price="10000",
        change="0",
        change_rate="0",
        volume=1,
        as_of="t",
        signals=(),
        provisional=False,
    )
    return PipelineResult(
        report_id=11,
        status=ReportStatus.DONE,
        header=header,
        strategy=strategy,
        summary=summary,
        tokens=0,
        cost_usd=Decimal("0"),
    )


def _judge(
    answer=ENTER,
    price="10000",
    positions=None,
    principles=None,
    roles=None,
    extractor=None,
    fail=False,
):
    tools = FakeTools()
    tools.payloads["get_quote"] = {"symbol": "000660", "price": price}
    runner = FakeRunner(
        answers={"buy_judge": answer}, fail_agents={"buy_judge"} if fail else None
    )
    positions = positions or FakePositions()
    decisions = FakeDecisions()
    judge = BuyJudgement(
        tools=tools,
        runner=runner,
        roles=roles or FakeRoles(),
        positions=positions,
        decisions=decisions,
        extractor=extractor,
        principles=principles,
        logger=MagicMock(),
        now_utc=lambda: NOW,
    )
    return judge, runner, positions, decisions, tools


async def test_enter_opens_position_at_quote_price_sc1():
    judge, runner, positions, decisions, tools = _judge(price="10000")
    cost = await judge(_target(), _result(), SETTING, "r")
    assert cost == (100, Decimal("0.01"))
    (d,) = decisions.rows
    assert d.decision == "enter" and d.score == 8 and d.report_id == 11
    assert d.price_at_decision == Decimal("10000") and d.gate["passed"] is True
    assert d.regime == "bull" and d.run_id == "run-buy_judge"
    (pos,) = positions.rows.values()
    assert pos["entry_price"] == Decimal("10000") and pos["stop_loss"] == Decimal(
        "9500"
    )
    assert pos["buy_decision_id"] == 1 and decisions.links == {1: pos["id"]}
    ctx = runner.runs[0]["reference_context"]
    for part in (
        "[리포트 요약]",
        "[투자 시나리오]",
        "[머리 사실",
        "[계좌 상태]",
        "[진입 규칙",
        "[활성 매매 원칙]\n없음",
        "[시장 체제]",
    ):
        assert part in ctx
    assert ("kis", "get_quote") in {(c[0].value, c[1]) for c in tools.calls}


async def test_gate_failure_becomes_watchlist_with_reasons():
    # 현재가가 올라 RR 이 1.6 이 되면 게이트에서 막힌다
    judge, _, positions, decisions, _ = _judge(price="10750")
    await judge(_target(), _result(), SETTING, "r")
    (d,) = decisions.rows
    assert d.decision == "skip" and d.skip_reason.startswith("GATE: ")
    assert "RR_BELOW_MIN" in d.skip_reason and d.gate["passed"] is False
    assert positions.rows == {}


async def test_llm_skip_keeps_its_reason_and_gate_reason():
    skip = ENTER.replace('"enter"', '"skip"').replace("null}", '"거래량 부족"}')
    judge, _, positions, decisions, _ = _judge(answer=skip)
    await judge(_target(), _result(), SETTING, "r")
    (d,) = decisions.rows
    assert d.skip_reason.startswith("거래량 부족 · GATE: DECISION_SKIP")
    assert positions.rows == {}


async def test_u9_parse_failure_skips_after_extractor():
    ex = FakeExtractor(None)
    judge, _, positions, decisions, _ = _judge(answer="점수 8점", extractor=ex)
    await judge(_target(), _result(), SETTING, "r")
    (d,) = decisions.rows
    assert (d.decision, d.skip_reason, d.rationale) == (
        "skip",
        "PARSE_FAILED",
        "점수 8점",
    )
    assert ex.calls == 1 and positions.rows == {}


async def test_incomplete_report_skips_without_agent():
    judge, runner, _, decisions, _ = _judge()
    assert await judge(_target(), _result(strategy=None), SETTING, "r") == (
        0,
        Decimal("0"),
    )
    assert runner.runs == [] and decisions.rows[0].skip_reason == "REPORT_INCOMPLETE"


async def test_role_unmapped_and_agent_failure():
    roles = FakeRoles({r: r.value for r in AgentRole if r is not AgentRole.BUY_JUDGE})
    judge, runner, _, decisions, _ = _judge(roles=roles)
    await judge(_target(), _result(), SETTING, "r")
    assert runner.runs == [] and decisions.rows[0].skip_reason == "ROLE_UNMAPPED"

    judge, _, _, decisions, _ = _judge(fail=True)
    await judge(_target(), _result(), SETTING, "r")
    assert decisions.rows[0].skip_reason.startswith("JUDGE_FAILED")


async def test_quote_unavailable_does_not_enter():
    judge, _, positions, decisions, tools = _judge()
    tools.fail.add("get_quote")
    await judge(_target(), _result(), SETTING, "r")
    assert decisions.rows[0].skip_reason == "QUOTE_UNAVAILABLE" and positions.rows == {}


async def test_regime_minimum_and_principles_recorded():
    principles = FakePrinciples(
        [ActivePrinciple(3, "갭 상승 다음 날은 진입하지 않는다")]
    )
    judge, runner, _, decisions, _ = _judge(principles=principles)
    await judge(_target(regime="strong_bear"), _result(), SETTING, "r")  # 최소 8점
    (d,) = decisions.rows
    assert d.decision == "enter" and d.principles_used == (3,)
    assert principles.calls == ["buy"]
    assert "갭 상승 다음 날" in runner.runs[0]["reference_context"]


async def test_last_slot_is_not_taken_twice_concurrently():
    positions = FakePositions()
    for i in range(9):
        positions.seed(symbol=f"9{i:05d}")
    judge, _, positions, decisions, _ = _judge(positions=positions)
    await asyncio.gather(
        judge(_target("000001"), _result(), SETTING, "r"),
        judge(_target("000002"), _result(), SETTING, "r"),
    )
    opened = [r for r in positions.rows.values() if r["symbol"] in {"000001", "000002"}]
    assert len(opened) == 1
    assert sorted(d.decision for d in decisions.rows) == ["enter", "skip"]
    assert any("NO_SLOT" in (d.skip_reason or "") for d in decisions.rows)


async def test_m3_position_open_failure_reverts_enter_decision():
    """중간 점검 M3: 진입 판단만 남고 포지션이 없는 상태를 만들지 않는다."""
    judge, _, positions, decisions, _ = _judge()

    async def boom(**kw):
        raise RuntimeError("db down")

    positions.open_position = boom
    import pytest

    with pytest.raises(RuntimeError):
        await judge(_target(), _result(), SETTING, "r")
    assert decisions.reverted == {1: "ENTRY_FAILED: db down"}
