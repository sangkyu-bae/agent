"""회차 실행 — 휴장 → 후보 → 스캔 → 상한 → 종목 분석 → 집계 (design §2.2, §10, U8)."""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

from src.application.market_analysis.pipeline import PipelineResult
from src.application.market_analysis.round_runner import RoundRunner
from src.domain.market_analysis.report import ReportStatus
from src.domain.market_analysis.round import SkipReason
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.value_objects import RoundKind

from .fakes import FakeHeld, FakeRounds, FakeTools

TODAY = date(2026, 11, 26)
NOW_UTC = datetime(2026, 11, 26, 1, 5)  # 서울 10:05
SETTING = dataclasses.replace(
    MarketAnalysisSetting.defaults(),
    kis_server_id="kis-1",
    run_as_user_id="7",
    ranking_kinds=("volume",),
    max_per_round=2,
    max_per_day=50,
    max_concurrent_stocks=2,
)


def _tools(
    symbols=("000001", "000002", "000003"),
    signaled=("000001", "000002", "000003"),
    index_day="2026-11-26",
):
    tools = FakeTools()
    tools.payloads["get_rankings"] = {
        "entries": [
            {"symbol": s, "name": f"종목{s}", "volume": i}
            for i, s in enumerate(symbols)
        ]
    }
    tools.payloads["scan_signals"] = {
        "signals": {
            "volume_spike": [
                {"symbol": s, "direction": "up", "provisional": True, "values": {}}
                for s in signaled
            ]
        }
    }
    tools.payloads["get_index_history"] = lambda args: {
        "index": args["index"],
        "bars": [
            {"date": "2026-11-25", "close": "4600.00", "provisional": False},
            {"date": index_day, "close": "4697.51", "provisional": True},
        ],
    }
    return tools


class FakePipeline:
    def __init__(self, *, fail=frozenset(), raise_on=frozenset()):
        self.targets = []
        self.fail = fail
        self.raise_on = raise_on
        self.active = 0
        self.max_active = 0

    async def run(self, target, setting, *, run_slots, request_id, today=None):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0)
        self.active -= 1
        self.targets.append(target)
        if target.symbol in self.raise_on:
            raise RuntimeError("boom")
        status = (
            ReportStatus.FAILED if target.symbol in self.fail else ReportStatus.DONE
        )
        return PipelineResult(
            report_id=len(self.targets),
            status=status,
            header=None,
            strategy="s",
            summary="m",
            tokens=100,
            cost_usd=Decimal("0.01"),
        )


def _runner(tools, pipeline=None, rounds=None, held=None, hook=None):
    rounds = rounds or FakeRounds()
    pipeline = pipeline or FakePipeline()
    runner = RoundRunner(
        tools=tools,
        pipeline=pipeline,
        rounds=rounds,
        held=held or FakeHeld(),
        logger=MagicMock(),
        now_utc=lambda: NOW_UTC,
        after_report=hook,
    )
    return runner, rounds, pipeline


async def _claim(rounds, kind=RoundKind.INTRADAY):
    from src.domain.market_analysis.value_objects import RoundTrigger

    return await rounds.try_claim(
        trade_date=TODAY,
        slot="10:00",
        kind=kind,
        trigger=RoundTrigger.AUTO,
        request_id="r",
    )


async def _run(runner, rounds, setting=SETTING, kind=RoundKind.INTRADAY):
    rid = await _claim(rounds, kind)
    await runner.run(
        round_id=rid, trade_date=TODAY, kind=kind, setting=setting, request_id="r"
    )
    return rounds.rounds[rid]


async def test_happy_path_caps_and_records():
    runner, rounds, pipeline = _runner(_tools())
    r = await _run(runner, rounds)

    assert r["status"] == "done"
    c = r["counts"]
    assert (c.candidates, c.signaled, c.analyzed, c.over_cap, c.failed) == (
        3,
        3,
        2,
        1,
        0,
    )
    assert (c.tokens, c.cost_usd) == (200, Decimal("0.02"))
    statuses = sorted(i["status"] for i in rounds.items.values())
    assert statuses == ["done", "done", "over_cap"]
    # 거래량 많은 순 → 000003, 000002 가 분석된다
    assert {t.symbol for t in pipeline.targets} == {"000003", "000002"}
    t = pipeline.targets[0]
    assert t.provisional is True and t.round_id == 1 and t.trade_date == TODAY
    assert "KOSPI" in t.market_context and "4697.51" in t.market_context
    assert t.signals[0]["rule"] == "volume_spike"
    done = [i for i in rounds.items.values() if i["status"] == "done"]
    assert all(i["report_id"] for i in done)


async def test_close_round_targets_are_not_provisional_unless_signal_says_so():
    tools = _tools()
    tools.payloads["scan_signals"] = {
        "signals": {
            "gap": [
                {
                    "symbol": "000001",
                    "direction": "up",
                    "provisional": False,
                    "values": {},
                }
            ]
        }
    }
    runner, rounds, pipeline = _runner(tools)
    await _run(runner, rounds, kind=RoundKind.CLOSE)
    assert pipeline.targets[0].provisional is False


async def test_holiday_skips_without_analysis_u8():
    runner, rounds, pipeline = _runner(_tools(index_day="2026-11-25"))
    r = await _run(runner, rounds)
    assert (r["status"], r["skip_reason"]) == ("skipped", SkipReason.HOLIDAY)
    assert pipeline.targets == [] and rounds.items == {}


async def test_duplicate_and_held_are_recorded_not_analyzed():
    rounds = FakeRounds()
    rounds.analyzed = {"000001"}
    runner, rounds, pipeline = _runner(
        _tools(), rounds=rounds, held=FakeHeld({"000002"})
    )
    await _run(runner, rounds)
    by_symbol = {i["symbol"]: i["status"] for i in rounds.items.values()}
    assert by_symbol == {"000001": "duplicate", "000002": "held", "000003": "done"}
    assert [t.symbol for t in pipeline.targets] == ["000003"]


async def test_failed_report_and_exception_mark_items_failed_but_round_done():
    runner, rounds, _ = _runner(
        _tools(), pipeline=FakePipeline(fail={"000003"}, raise_on={"000002"})
    )
    r = await _run(runner, rounds)
    assert r["status"] == "done"
    assert r["counts"].failed == 2 and r["counts"].analyzed == 0
    errors = {
        i["symbol"]: i["error"]
        for i in rounds.items.values()
        if i["status"] == "failed"
    }
    assert errors["000002"].startswith("PIPELINE_ERROR")
    assert errors["000003"] == "REPORT_FAILED"


async def test_missing_configuration_fails_round():
    runner, rounds, _ = _runner(_tools())
    r = await _run(
        runner, rounds, setting=dataclasses.replace(SETTING, run_as_user_id=None)
    )
    assert (r["status"], r["error"]) == ("failed", "RUN_AS_USER_MISSING")
    runner, rounds, _ = _runner(_tools())
    r = await _run(
        runner, rounds, setting=dataclasses.replace(SETTING, kis_server_id=None)
    )
    assert (r["status"], r["error"]) == ("failed", "KIS_NOT_CONFIGURED")


async def test_concurrent_stock_limit():
    pipeline = FakePipeline()
    runner, rounds, _ = _runner(_tools(), pipeline=pipeline)
    await _run(
        runner,
        rounds,
        setting=dataclasses.replace(SETTING, max_per_round=3, max_concurrent_stocks=1),
    )
    assert pipeline.max_active == 1 and len(pipeline.targets) == 3


async def test_after_report_hook_runs_and_its_failure_is_contained():
    seen = []

    async def hook(target, result, setting, request_id):
        seen.append(target.symbol)
        raise RuntimeError("judge exploded")

    runner, rounds, _ = _runner(_tools(), hook=hook)
    r = await _run(runner, rounds)
    assert sorted(seen) == ["000002", "000003"]
    assert r["status"] == "done" and r["counts"].analyzed == 2


async def test_no_signals_finishes_done_with_zero():
    runner, rounds, pipeline = _runner(_tools(signaled=()))
    r = await _run(runner, rounds)
    assert (
        r["status"] == "done" and r["counts"].signaled == 0 and pipeline.targets == []
    )


# ── module-6 통합: 체제 → 보유 관리 → 분석 → 매수 판단 → 성과 ────────────────


class FakeManager:
    def __init__(self, order):
        self.order = order
        self.calls = []

    async def manage(self, setting, *, regime, provisional, run_slots, request_id):
        from src.application.market_analysis.positions import ManageResult

        self.order.append("manage")
        self.calls.append((regime, provisional))
        return ManageResult(closed=(1,), tokens=50, cost_usd=Decimal("0.005"))


class FakePerformance:
    def __init__(self):
        self.calls = []

    async def record(self, *, trade_date, snapshot, setting, request_id):
        self.calls.append(trade_date)


def _integrated(tools=None, roles=None, kind_order=None):
    from src.application.market_analysis.regime import MarketRegimeService

    from .fakes import FakeRegimes

    order = kind_order if kind_order is not None else []
    tools = tools or _tools()
    original = tools.call

    async def traced(**kw):
        if kw["tool"] == "get_rankings":
            order.append("candidates")
        return await original(**kw)

    tools.call = traced
    regimes = FakeRegimes()
    manager = FakeManager(order)
    performance = FakePerformance()
    judged = []

    async def judge(target, result, setting, request_id):
        judged.append(target)
        return (30, Decimal("0.003"))

    rounds = FakeRounds()
    runner = RoundRunner(
        tools=tools,
        pipeline=FakePipeline(),
        rounds=rounds,
        held=FakeHeld(),
        logger=MagicMock(),
        now_utc=lambda: NOW_UTC,
        after_report=judge,
        market=MarketRegimeService(tools=tools, regimes=regimes, logger=MagicMock()),
        positions=manager,
        performance=performance,
        roles=roles,
    )
    return runner, rounds, order, manager, performance, judged, regimes


async def test_positions_managed_before_candidates_and_costs_summed():
    runner, rounds, order, manager, perf, judged, regimes = _integrated()
    r = await _run(runner, rounds)
    assert order[:2] == ["manage", "candidates"]
    assert manager.calls == [("neutral", True)]
    assert [t.regime for t in judged] == ["neutral", "neutral"]
    assert judged[0].market_context.startswith("[시장 체제]")
    # 분석 100×2 + 판단 30×2 + 보유 관리 50
    assert r["counts"].tokens == 310 and r["counts"].cost_usd == Decimal("0.031")
    done = [i for i in rounds.items.values() if i["status"] == "done"]
    assert all(i["tokens"] == 130 for i in done)
    assert TODAY in regimes.regimes
    assert perf.calls == []  # 장중 회차는 성과 스냅샷을 남기지 않는다


async def test_close_round_records_performance():
    runner, rounds, _, _, perf, _, _ = _integrated()
    await _run(runner, rounds, kind=RoundKind.CLOSE)
    assert perf.calls == [TODAY]


async def test_holiday_skips_before_position_management():
    runner, rounds, order, manager, _, _, regimes = _integrated(
        tools=_tools(index_day="2026-11-25")
    )
    r = await _run(runner, rounds)
    assert r["status"] == "skipped" and manager.calls == [] and regimes.regimes == {}


async def test_missing_judge_roles_fail_round_before_any_call():
    from src.domain.market_analysis.value_objects import AgentRole

    from .fakes import FakeRoles

    roles = FakeRoles({r: r.value for r in AgentRole if r is not AgentRole.SELL_JUDGE})
    runner, rounds, order, manager, _, _, _ = _integrated(roles=roles)
    r = await _run(runner, rounds)
    assert (r["status"], r["error"]) == ("failed", "ROLE_UNMAPPED(sell_judge)")
    assert order == [] and manager.calls == []


async def test_position_management_failure_does_not_block_analysis():
    runner, rounds, _, manager, _, judged, _ = _integrated()

    async def boom(*a, **k):
        raise RuntimeError("quotes down")

    manager.manage = boom
    r = await _run(runner, rounds)
    assert r["status"] == "done" and len(judged) == 2


# ── 중간 점검 I1: KIS 를 쓸 수 없으면 '신호 없음'이 아니라 failed ───────────────


async def test_kis_unavailable_fails_round_instead_of_done_zero():

    for code in ("SERVER_UNAVAILABLE", "KIS_AUTH_FAILED"):
        tools = _tools()
        tools.fail = {"get_index_history", "get_rankings", "scan_signals"}
        tools.fail_code = code
        runner, rounds, pipeline = _runner(tools)
        r = await _run(runner, rounds)
        assert (r["status"], r["error"]) == ("failed", f"KIS_UNAVAILABLE({code})")
        assert pipeline.targets == [] and rounds.items == {}


async def test_transient_index_error_does_not_fail_round():
    tools = _tools()
    tools.fail = {"get_index_history"}  # KIS_TIMEOUT — 일시 오류는 neutral 로 계속
    runner, rounds, pipeline = _runner(tools)
    r = await _run(runner, rounds)
    assert r["status"] == "done" and len(pipeline.targets) == 2


async def test_scan_rejected_everywhere_fails_round():
    tools = _tools()
    tools.fail = {"scan_signals"}
    tools.fail_code = "INVALID_ARGUMENT"
    runner, rounds, pipeline = _runner(tools)
    r = await _run(runner, rounds)
    assert (r["status"], r["error"]) == ("failed", "SCAN_FAILED(INVALID_ARGUMENT)")
    assert pipeline.targets == []
