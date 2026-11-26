"""회차 틱 루프 (lifespan 태스크) — design DD6."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from src.infrastructure.market_analysis.ticker import MarketAnalysisTicker


class FakeScheduler:
    def __init__(self, fail_first: bool = False):
        self.recovered = 0
        self.ticks = 0
        self.stopped = 0
        self.fail_first = fail_first

    async def recover(self, request_id):
        self.recovered += 1
        return 0

    async def tick(self, request_id):
        self.ticks += 1
        if self.fail_first and self.ticks == 1:
            raise RuntimeError("db down")
        return []

    async def stop(self):
        self.stopped += 1


async def _spin(ticker, until):
    for _ in range(200):
        if until():
            return
        await asyncio.sleep(0.005)


async def test_recovers_once_then_ticks_repeatedly():
    s = FakeScheduler()
    t = MarketAnalysisTicker(s, interval_sec=0.01, logger=MagicMock())
    t.start()
    await _spin(t, lambda: s.ticks >= 3)
    await t.stop()
    assert s.recovered == 1 and s.ticks >= 3 and s.stopped == 1
    assert not t.running


async def test_tick_exception_does_not_stop_the_loop():
    s = FakeScheduler(fail_first=True)
    logger = MagicMock()
    t = MarketAnalysisTicker(s, interval_sec=0.01, logger=logger)
    t.start()
    await _spin(t, lambda: s.ticks >= 2)
    await t.stop()
    assert s.ticks >= 2
    assert logger.error.called


async def test_start_twice_keeps_one_loop_and_stop_is_idempotent():
    s = FakeScheduler()
    t = MarketAnalysisTicker(s, interval_sec=0.01, logger=MagicMock())
    t.start()
    t.start()
    await _spin(t, lambda: s.ticks >= 1)
    await t.stop()
    await t.stop()
    assert s.recovered == 1
