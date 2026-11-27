"""틱 1회 — 시각 판정 → 선점 → 건너뜀/실행, 기동 시 회수
(design §2.2, U7·U11·U14, Plan SC-2)."""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from src.application.market_analysis.scheduler import RoundScheduler
from src.domain.market_analysis.round import SkipReason
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.domain.market_analysis.value_objects import RoundKind

from .fakes import FakeRounds

ON = dataclasses.replace(MarketAnalysisSetting.defaults(), enabled=True)
THU_1005 = datetime(2026, 11, 26, 1, 5)  # 목 서울 10:05
SAT_1005 = datetime(2026, 11, 28, 1, 5)
THU_1815 = datetime(2026, 11, 26, 9, 15)  # 서울 18:15


class FakeSettings:
    def __init__(self, setting):
        self.setting = setting

    async def get(self, request_id):
        return self.setting


class FakeRunner:
    def __init__(self, gate: asyncio.Event | None = None):
        self.calls = []
        self.gate = gate

    async def run(self, *, round_id, trade_date, kind, setting, request_id):
        self.calls.append((round_id, trade_date, kind))
        if self.gate:
            await self.gate.wait()


def _scheduler(setting=ON, now=THU_1005, rounds=None, runner=None):
    rounds = rounds or FakeRounds()
    runner = runner or FakeRunner()
    s = RoundScheduler(
        settings=FakeSettings(setting),
        rounds=rounds,
        runner=runner,
        logger=MagicMock(),
        now_utc=lambda: now,
    )
    return s, rounds, runner


async def test_disabled_switch_records_skip_and_never_runs_u7():
    s, rounds, runner = _scheduler(setting=dataclasses.replace(ON, enabled=False))
    actions = await s.tick("r")
    assert actions == [("10:00", f"skipped:{SkipReason.DISABLED}")]
    (r,) = rounds.rounds.values()
    assert (r["status"], r["skip_reason"]) == ("skipped", SkipReason.DISABLED)
    assert runner.calls == []


async def test_same_slot_is_claimed_once_u14():
    s, rounds, runner = _scheduler()
    assert await s.tick("r") == [("10:00", "started")]
    await s.wait_idle()
    assert await s.tick("r") == []  # 30초 뒤 같은 슬롯 — 이미 선점됨
    assert len(runner.calls) == 1 and len(rounds.rounds) == 1


async def test_weekend_is_skipped():
    s, rounds, runner = _scheduler(now=SAT_1005)
    assert await s.tick("r") == [("10:00", f"skipped:{SkipReason.WEEKEND}")]
    assert runner.calls == []


async def test_close_slot_runs_with_close_kind():
    s, _, runner = _scheduler(now=THU_1815)
    await s.tick("r")
    await s.wait_idle()
    assert runner.calls[0][2] is RoundKind.CLOSE


async def test_busy_when_a_round_is_still_running():
    gate = asyncio.Event()
    rounds = FakeRounds()
    s, rounds, runner = _scheduler(
        rounds=rounds,
        runner=FakeRunner(gate),
        setting=dataclasses.replace(ON, round_times=("10:00", "10:05")),
    )
    actions = await s.tick("r")
    assert actions == [("10:00", "started"), ("10:05", f"skipped:{SkipReason.BUSY}")]
    gate.set()
    await s.wait_idle()


async def test_busy_when_another_instance_runs():
    rounds = FakeRounds()
    from datetime import date

    from src.domain.market_analysis.value_objects import RoundTrigger

    await rounds.try_claim(
        trade_date=date(2026, 11, 26),
        slot="09:00",
        kind=RoundKind.INTRADAY,
        trigger=RoundTrigger.MANUAL,
        request_id="r",
    )
    s, rounds, runner = _scheduler(rounds=rounds)
    assert await s.tick("r") == [("10:00", f"skipped:{SkipReason.BUSY}")]


async def test_recover_abandons_running_rounds_u11():
    rounds = FakeRounds()
    rounds.rounds[1] = {"status": "running"}
    s, rounds, _ = _scheduler(rounds=rounds)
    assert await s.recover("r") == 1
    assert rounds.rounds[1]["status"] == "abandoned"


async def test_stop_cancels_running_round():
    gate = asyncio.Event()
    s, _, _ = _scheduler(runner=FakeRunner(gate))
    await s.tick("r")
    assert s.running
    await s.stop()
    assert not s.running


# ── module-8: 지금 실행 (trigger=manual) ─────────────────────────────────────


async def test_run_now_ignores_switch_and_claims_manual_slot():
    from src.domain.market_analysis.value_objects import RoundTrigger

    s, rounds, runner = _scheduler(setting=dataclasses.replace(ON, enabled=False))
    rid = await s.run_now(RoundKind.CLOSE, "r")
    await s.wait_idle()
    assert rid == 1 and runner.calls == [(1, THU_1005.date(), RoundKind.CLOSE)]
    r = rounds.rounds[1]
    assert (r["slot"], r["trigger"], r["kind"]) == (
        "10:05",
        RoundTrigger.MANUAL,
        RoundKind.CLOSE,
    )


@pytest.mark.parametrize(
    ("now", "kind"),
    [(THU_1005, RoundKind.INTRADAY), (THU_1815, RoundKind.CLOSE)],
    ids=["10:05-intraday", "18:15-close"],
)
async def test_run_now_without_kind_follows_the_clock(now, kind):
    """2026-11-27: 11:38 수동 회차가 장마감으로 돌아 장중 값을 확정값처럼 다뤘다.
    종류를 안 주면 자동 회차와 같은 규칙(15:30 기준)으로 정한다."""
    s, rounds, runner = _scheduler(now=now)
    rid = await s.run_now(None, "r")
    await s.wait_idle()
    assert rounds.rounds[rid]["kind"] is kind
    assert runner.calls[0][2] is kind


async def test_run_now_is_refused_while_a_round_runs_or_same_minute_twice():
    gate = asyncio.Event()
    s, rounds, runner = _scheduler(runner=FakeRunner(gate))
    assert await s.run_now(RoundKind.INTRADAY, "r") == 1
    assert await s.run_now(RoundKind.INTRADAY, "r") is None  # 실행 중
    gate.set()
    await s.wait_idle()
    rounds.rounds[1]["status"] = "done"
    assert await s.run_now(RoundKind.INTRADAY, "r") is None  # 같은 분 = 같은 슬롯
