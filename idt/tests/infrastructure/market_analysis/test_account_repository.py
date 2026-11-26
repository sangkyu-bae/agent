"""가상 계좌 저장소 (SQLite 실제 세션) — 포지션
진입·청산·조정 · 판단 · 체제·성과 덮어쓰기."""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncGenerator
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.domain.market_analysis.account import DecisionDraft, ExitReason, RegimeResult
from src.domain.market_analysis.value_objects import Regime
from src.infrastructure.market_analysis.account_repository import (
    DecisionRepository,
    PositionRepository,
    RegimeRepository,
)
from src.infrastructure.market_analysis.models import (
    MaDecisionModel,
    MaEquitySnapshotModel,
    MaMarketRegimeModel,
    MaPositionModel,
)
from src.infrastructure.persistence.models.base import Base

D = Decimal
NOW = datetime(2026, 11, 26, 1, 10)


@pytest.fixture
async def factory() -> AsyncGenerator[async_sessionmaker, None]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    tables = [
        MaDecisionModel.__table__,
        MaPositionModel.__table__,
        MaMarketRegimeModel.__table__,
        MaEquitySnapshotModel.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    finally:
        await engine.dispose()
        os.unlink(tmp.name)


def _draft(**kw) -> DecisionDraft:
    base = dict(
        kind="buy",
        symbol="000660",
        name="SK하이닉스",
        decision="enter",
        created_at=NOW,
        report_id=3,
        score=8,
        target_price=D("12000"),
        stop_loss=D("9500"),
        rationale="수급 개선",
        gate={"passed": True},
        principles_used=(2, 5),
        price_at_decision=D("10000"),
        regime="bull",
    )
    base.update(kw)
    return DecisionDraft(**base)


async def test_open_join_rationale_close_and_closed_trades(factory):
    decisions = DecisionRepository(factory, MagicMock())
    positions = PositionRepository(factory, MagicMock())
    did = await decisions.add(_draft(), "r")
    pid = await positions.open_position(
        symbol="000660",
        name="SK하이닉스",
        sector="반도체",
        entry_price=D("10000"),
        entry_at=NOW,
        target_price=D("12000"),
        stop_loss=D("9500"),
        buy_decision_id=did,
        request_id="r",
    )
    await decisions.link_position(decision_id=did, position_id=pid, request_id="r")

    (p,) = await positions.open_positions("r")
    assert (p.id, p.symbol, p.entry_price, p.buy_rationale) == (
        pid,
        "000660",
        D("10000"),
        "수급 개선",
    )
    assert p.slot_weight == D("1.000")
    assert await positions.held_symbols("r") == {"000660"}

    await positions.adjust_levels(
        position_id=pid, target_price=D("13000"), stop_loss=D("9900"), request_id="r"
    )
    (p,) = await positions.open_positions("r")
    assert (p.target_price, p.stop_loss) == (D("13000"), D("9900"))

    await positions.close_position(
        position_id=pid,
        exit_price=D("9900"),
        exit_at=NOW,
        reason=ExitReason.STOP,
        profit_rate=D("-1.0000"),
        holding_days=0,
        request_id="r",
    )
    assert await positions.open_positions("r") == []
    (t,) = await positions.closed_trades("r")
    assert (t.profit_rate, t.slot_weight, t.holding_days) == (
        D("-1.0000"),
        D("1.000"),
        0,
    )
    # 이미 닫힌 포지션은 다시 닫히거나 조정되지 않는다
    await positions.adjust_levels(
        position_id=pid, target_price=D("1"), stop_loss=D("1"), request_id="r"
    )
    async with factory() as s:
        row = await s.get(MaPositionModel, pid)
        assert (row.exit_reason, row.stop_loss) == ("stop", D("9900"))
        decision = await s.get(MaDecisionModel, did)
        assert decision.position_id == pid and decision.principles_used == [2, 5]
        assert decision.gate == {"passed": True}


async def test_regime_and_snapshot_upsert_and_first_closes(factory):
    repo = RegimeRepository(factory, MagicMock())
    assert await repo.first_closes("r") is None
    first = RegimeResult(Regime.BULL, D("4600"), D("4550"), D("4500"), D("2.10"), False)
    await repo.save_regime(
        trade_date=date(2026, 11, 25),
        result=first,
        kosdaq_close=D("900"),
        bars=80,
        request_id="r",
    )
    later = RegimeResult(Regime.NEUTRAL, D("4700"), None, None, None, True)
    await repo.save_regime(
        trade_date=date(2026, 11, 26),
        result=later,
        kosdaq_close=None,
        bars=40,
        request_id="r",
    )
    await repo.save_regime(
        trade_date=date(2026, 11, 26),
        result=first,
        kosdaq_close=D("910"),
        bars=80,
        request_id="r",
    )
    assert await repo.first_closes("r") == (D("4600.00"), D("900.00"))
    async with factory() as s:
        rows = (await s.execute(select(MaMarketRegimeModel))).scalars().all()
        assert len(rows) == 2
        today = await s.get(MaMarketRegimeModel, date(2026, 11, 26))
        assert today.regime == "bull" and today.basis == {
            "r20": "2.10",
            "bars": 80,
            "insufficient": False,
        }

    for rate in (D("1.5"), D("2.25")):
        await repo.save_snapshot(
            trade_date=date(2026, 11, 26),
            realized_cum_rate=rate,
            open_positions=3,
            used_slots=D("3"),
            kospi_cum_rate=D("2.1739"),
            kosdaq_cum_rate=None,
            request_id="r",
        )
    async with factory() as s:
        snaps = (await s.execute(select(MaEquitySnapshotModel))).scalars().all()
        assert len(snaps) == 1 and snaps[0].realized_cum_rate == D("2.2500")
