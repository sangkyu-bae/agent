"""회차 저장소 (SQLite 실제 세션) — UNIQUE 선점 · 종목
행 · 회수 · 보유 조회 (design §3.3, U11·U14)."""

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
from src.domain.market_analysis.round import RoundCounts, RoundItemDraft
from src.domain.market_analysis.value_objects import (
    ItemStatus,
    RoundKind,
    RoundStatus,
    RoundTrigger,
)
from src.infrastructure.market_analysis.account_repository import PositionRepository
from src.infrastructure.market_analysis.models import (
    MaPositionModel,
    MaReportModel,
    MaRoundItemModel,
    MaRoundModel,
    MaSettingModel,
)
from src.infrastructure.market_analysis.round_repository import (
    RoundRepository,
    SessionSettingReader,
)
from src.infrastructure.persistence.models.base import Base

DAY = date(2026, 11, 26)


@pytest.fixture
async def factory() -> AsyncGenerator[async_sessionmaker, None]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(
                c,
                tables=[
                    MaRoundModel.__table__,
                    MaReportModel.__table__,
                    MaRoundItemModel.__table__,
                    MaPositionModel.__table__,
                    MaSettingModel.__table__,
                ],
            )
        )
    try:
        yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    finally:
        await engine.dispose()
        os.unlink(tmp.name)


async def _claim(repo, slot="10:00", trigger=RoundTrigger.AUTO):
    return await repo.try_claim(
        trade_date=DAY,
        slot=slot,
        kind=RoundKind.INTRADAY,
        trigger=trigger,
        request_id="r",
    )


async def test_claim_is_unique_per_slot_and_trigger_u14(factory):
    repo = RoundRepository(factory, MagicMock())
    first = await _claim(repo)
    assert first is not None
    assert await _claim(repo) is None
    assert await _claim(repo, trigger=RoundTrigger.MANUAL) is not None
    assert await repo.any_running(exclude_id=first, request_id="r") is True


async def test_skip_items_and_finish(factory):
    repo = RoundRepository(factory, MagicMock())
    rid = await _claim(repo)
    ids = await repo.add_items(
        round_id=rid,
        request_id="r",
        items=[
            RoundItemDraft(
                "005930", "삼성전자", ({"rule": "gap"},), ItemStatus.QUEUED.value
            ),
            RoundItemDraft("000660", "SK하이닉스", (), ItemStatus.OVER_CAP.value),
        ],
    )
    await repo.update_item(
        item_id=ids["005930"],
        status=ItemStatus.DONE,
        report_id=7,
        tokens=800,
        cost_usd=Decimal("0.08"),
        request_id="r",
    )
    await repo.finish_round(
        round_id=rid,
        status=RoundStatus.DONE,
        error=None,
        request_id="r",
        counts=RoundCounts(
            candidates=30,
            signaled=2,
            analyzed=1,
            over_cap=1,
            tokens=800,
            cost_usd=Decimal("0.08"),
        ),
    )
    async with factory() as s:
        r = await s.get(MaRoundModel, rid)
        items = (
            (await s.execute(select(MaRoundItemModel).order_by(MaRoundItemModel.id)))
            .scalars()
            .all()
        )
    assert (r.status, r.candidates, r.signaled, r.analyzed, r.over_cap) == (
        "done",
        30,
        2,
        1,
        1,
    )
    assert (r.total_tokens, Decimal(str(r.total_cost_usd))) == (800, Decimal("0.08"))
    assert r.finished_at is not None
    assert [(i.symbol, i.status, i.report_id) for i in items] == [
        ("005930", "done", 7),
        ("000660", "over_cap", None),
    ]
    assert items[0].signals == [{"rule": "gap"}]

    other = await _claim(repo, slot="14:00")
    await repo.skip(round_id=other, reason="DISABLED", request_id="r")
    async with factory() as s:
        r2 = await s.get(MaRoundModel, other)
    assert (r2.status, r2.skip_reason) == ("skipped", "DISABLED")


async def test_analyzed_symbols_excludes_failed_and_waiting_caps(factory):
    repo = RoundRepository(factory, MagicMock())
    rid = await _claim(repo)
    await repo.add_items(
        round_id=rid,
        request_id="r",
        items=[
            RoundItemDraft("A", "a", (), ItemStatus.DONE.value),
            RoundItemDraft("B", "b", (), ItemStatus.ANALYZING.value),
            RoundItemDraft("C", "c", (), ItemStatus.FAILED.value),
            RoundItemDraft("D", "d", (), ItemStatus.OVER_CAP.value),
        ],
    )
    assert await repo.analyzed_symbols(trade_date=DAY, request_id="r") == {"A", "B"}
    assert (
        await repo.analyzed_symbols(trade_date=date(2026, 11, 27), request_id="r")
        == set()
    )


async def test_abandon_running_u11(factory):
    repo = RoundRepository(factory, MagicMock())
    rid = await _claim(repo)
    await repo.add_items(
        round_id=rid,
        request_id="r",
        items=[
            RoundItemDraft("A", "a", (), ItemStatus.ANALYZING.value),
            RoundItemDraft("B", "b", (), ItemStatus.DONE.value),
        ],
    )
    assert await repo.abandon_running("r") == 1
    async with factory() as s:
        r = await s.get(MaRoundModel, rid)
        items = {
            i.symbol: i for i in (await s.execute(select(MaRoundItemModel))).scalars()
        }
    assert r.status == "abandoned"
    assert (items["A"].status, items["A"].error) == ("failed", "ABANDONED")
    assert items["B"].status == "done"
    assert await repo.any_running(exclude_id=None, request_id="r") is False


async def test_open_position_reader(factory):
    now = datetime(2026, 11, 26)
    async with factory() as s, s.begin():
        for symbol, status in (("A", "open"), ("B", "closed")):
            s.add(
                MaPositionModel(
                    symbol=symbol,
                    status=status,
                    slot_weight=Decimal("1"),
                    entry_price=Decimal("1"),
                    entry_at=now,
                    target_price=Decimal("2"),
                    stop_loss=Decimal("0.5"),
                    created_at=now,
                    updated_at=now,
                )
            )
    assert await PositionRepository(factory, MagicMock()).held_symbols("r") == {"A"}


async def test_session_setting_reader_defaults(factory):
    s = await SessionSettingReader(factory, MagicMock()).get("r")
    assert s.enabled is False


async def test_abandon_running_also_fails_running_reports_of_that_round(factory):
    """중간 점검 I2: 재시작 회수가 그 회차의 running 리포트도 failed 로 닫는다."""

    repo = RoundRepository(factory, MagicMock())
    rid = await _claim(repo)
    now = datetime(2026, 11, 26)
    async with factory() as s, s.begin():
        for status, round_id in (("running", rid), ("done", rid), ("running", None)):
            s.add(
                MaReportModel(
                    symbol="A",
                    name="a",
                    trade_date=DAY,
                    round_id=round_id,
                    status=status,
                    provisional=False,
                    signals=[],
                    created_at=now,
                )
            )
    await repo.abandon_running("r")
    async with factory() as s:
        rows = (
            await s.execute(select(MaReportModel).order_by(MaReportModel.id))
        ).scalars()
        assert [r.status for r in rows] == ["failed", "done", "running"]
