"""지수 일봉 저장소 (SQLite 실제 세션).

마지막 저장일 · 덮어쓰기 · 기간 조회 · 체제 기록.

Design Ref: market-index-ytd-chart §3.3, §3.4.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncGenerator
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.domain.market_analysis.index_chart import IndexBar
from src.infrastructure.market_analysis.index_daily_repository import (
    IndexDailyRepository,
)
from src.infrastructure.market_analysis.models import (
    MaIndexDailyModel,
    MaMarketRegimeModel,
)
from src.infrastructure.persistence.models.base import Base

D = Decimal
Y0 = date(2026, 1, 1)


@pytest.fixture
async def factory() -> AsyncGenerator[async_sessionmaker, None]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    tables = [MaIndexDailyModel.__table__, MaMarketRegimeModel.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    finally:
        await engine.dispose()
        os.unlink(tmp.name)


def _repo(factory) -> IndexDailyRepository:
    return IndexDailyRepository(factory, MagicMock())


def _bar(index: str, day: date, close: str, *, provisional: bool = False) -> IndexBar:
    c = D(close)
    return IndexBar(
        index=index,
        day=day,
        open=c,
        high=c + 1,
        low=c - 1,
        close=c,
        provisional=provisional,
    )


async def test_last_date_none_when_empty(factory):
    assert await _repo(factory).last_date("KOSPI", Y0, "r") is None


async def test_upsert_then_last_date_per_index(factory):
    repo = _repo(factory)
    n = await repo.upsert(
        [
            _bar("KOSPI", date(2026, 1, 2), "2500"),
            _bar("KOSPI", date(2026, 1, 5), "2510"),
            _bar("KOSDAQ", date(2026, 1, 2), "700"),
        ],
        "r",
    )
    assert n == 3
    assert await repo.last_date("KOSPI", Y0, "r") == date(2026, 1, 5)
    assert await repo.last_date("KOSDAQ", Y0, "r") == date(2026, 1, 2)


async def test_last_date_ignores_days_before_since(factory):
    repo = _repo(factory)
    await repo.upsert([_bar("KOSPI", date(2025, 12, 30), "2400")], "r")
    assert await repo.last_date("KOSPI", Y0, "r") is None


async def test_upsert_overwrites_and_skips_provisional(factory):
    # Plan FR-04 · FR-09: 장중 봉은 저장하지 않고, 같은 날은 덮어쓴다
    repo = _repo(factory)
    await repo.upsert([_bar("KOSPI", date(2026, 1, 2), "2500")], "r")
    n = await repo.upsert(
        [
            _bar("KOSPI", date(2026, 1, 2), "2501.5"),
            _bar("KOSPI", date(2026, 1, 5), "2600", provisional=True),
        ],
        "r",
    )
    assert n == 1
    bars = await repo.bars("KOSPI", Y0, date(2026, 12, 31), "r")
    assert [(b.day, b.close) for b in bars] == [(date(2026, 1, 2), D("2501.50"))]
    assert bars[0].high == D("2502.50")
    assert bars[0].provisional is False


async def test_bars_range_and_order(factory):
    repo = _repo(factory)
    await repo.upsert(
        [
            _bar("KOSPI", date(2026, 1, 6), "3"),
            _bar("KOSPI", date(2026, 1, 2), "1"),
            _bar("KOSPI", date(2026, 1, 5), "2"),
            _bar("KOSDAQ", date(2026, 1, 5), "9"),
        ],
        "r",
    )
    bars = await repo.bars("KOSPI", date(2026, 1, 2), date(2026, 1, 5), "r")
    assert [b.day for b in bars] == [date(2026, 1, 2), date(2026, 1, 5)]
    assert all(b.index == "KOSPI" for b in bars)


async def test_regimes_in_range(factory):
    async with factory() as session, session.begin():
        for day, regime in (
            (date(2025, 12, 30), "bull"),
            (date(2026, 11, 25), "bear"),
            (date(2026, 11, 26), "strong_bear"),
        ):
            session.add(
                MaMarketRegimeModel(
                    trade_date=day, regime=regime, created_at=datetime(2026, 11, 26)
                )
            )
    got = await _repo(factory).regimes(Y0, date(2026, 11, 27), "r")
    assert got == [(date(2026, 11, 25), "bear"), (date(2026, 11, 26), "strong_bear")]
