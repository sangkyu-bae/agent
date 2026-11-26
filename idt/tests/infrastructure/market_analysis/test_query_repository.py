"""조회 저장소 (SQLite 실제 세션) — 형식(UTC·float)·조인·페이지·없음."""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncGenerator
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.infrastructure.market_analysis.models import (
    MaDecisionModel,
    MaEquitySnapshotModel,
    MaEvidenceModel,
    MaJournalModel,
    MaMarketRegimeModel,
    MaPositionModel,
    MaPrincipleModel,
    MaReportModel,
    MaReportSectionModel,
    MaRoundItemModel,
    MaRoundModel,
)
from src.infrastructure.market_analysis.query_repository import QueryRepository
from src.infrastructure.persistence.models.base import Base

D = Decimal
T0 = datetime(2026, 11, 20, 1, 0)
T1 = datetime(2026, 11, 26, 6, 40)
DAY = date(2026, 11, 26)
MODELS = [
    MaRoundModel,
    MaRoundItemModel,
    MaReportModel,
    MaReportSectionModel,
    MaEvidenceModel,
    MaDecisionModel,
    MaPositionModel,
    MaJournalModel,
    MaPrincipleModel,
    MaMarketRegimeModel,
    MaEquitySnapshotModel,
]


@pytest.fixture
async def factory() -> AsyncGenerator[async_sessionmaker, None]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(c, tables=[m.__table__ for m in MODELS])
        )
    try:
        yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    finally:
        await engine.dispose()
        os.unlink(tmp.name)


async def _seed(factory) -> dict[str, int]:
    async with factory() as s, s.begin():
        rnd = MaRoundModel(
            trade_date=DAY,
            slot="18:10",
            kind="close",
            run_trigger="auto",
            status="done",
            candidates=5,
            signaled=3,
            analyzed=2,
            over_cap=0,
            failed=1,
            total_tokens=900,
            total_cost_usd=D("0.31"),
            started_at=T1,
            finished_at=T1,
        )
        s.add(rnd)
        await s.flush()
        rep = MaReportModel(
            symbol="000660",
            name="SK하이닉스",
            trade_date=DAY,
            round_id=rnd.id,
            provisional=False,
            signals=[{"rule": "gap"}, {"rule": "volume_spike"}],
            header_facts={"price": "10000"},
            strategy="시나리오",
            summary="요약",
            regime="bull",
            status="done",
            tokens=800,
            cost_usd=D("0.3"),
            created_at=T0,
        )
        s.add(rep)
        await s.flush()
        s.add_all(
            [
                MaRoundItemModel(
                    round_id=rnd.id,
                    symbol="000660",
                    name="SK하이닉스",
                    signals=[{"rule": "gap"}],
                    status="done",
                    report_id=rep.id,
                    tokens=800,
                    cost_usd=D("0.3"),
                    created_at=T1,
                ),
                MaReportSectionModel(
                    report_id=rep.id,
                    role="section_technical",
                    status="done",
                    content="본문",
                    tokens=100,
                    cost_usd=D("0.01"),
                    created_at=T0,
                ),
                MaEvidenceModel(
                    report_id=rep.id,
                    source="kis",
                    tool="get_quote",
                    args={"symbol": "000660"},
                    payload="x" * 30_000,
                    is_error=False,
                    fetched_at=T0,
                ),
            ]
        )
        buy = MaDecisionModel(
            kind="buy",
            symbol="000660",
            name="SK하이닉스",
            report_id=rep.id,
            score=8,
            decision="enter",
            price_at_decision=D("10000"),
            gate={"passed": True},
            principles_used=[1],
            provisional=False,
            created_at=T0,
        )
        skip = MaDecisionModel(
            kind="buy",
            symbol="005930",
            decision="skip",
            skip_reason="GATE: NO_SLOT",
            provisional=False,
            created_at=T1,
        )
        s.add_all([buy, skip])
        await s.flush()
        pos = MaPositionModel(
            symbol="000660",
            name="SK하이닉스",
            status="closed",
            slot_weight=D("1"),
            entry_price=D("10000"),
            entry_at=T0,
            target_price=D("12000"),
            stop_loss=D("9500"),
            exit_price=D("9400"),
            exit_at=T1,
            exit_reason="stop",
            profit_rate=D("-6"),
            holding_days=6,
            buy_decision_id=buy.id,
            created_at=T0,
            updated_at=T1,
        )
        held = MaPositionModel(
            symbol="035420",
            status="open",
            slot_weight=D("1"),
            entry_price=D("200000"),
            entry_at=T1,
            target_price=D("230000"),
            stop_loss=D("190000"),
            created_at=T1,
            updated_at=T1,
        )
        s.add_all([pos, held])
        await s.flush()
        buy.position_id = pos.id
        s.add_all(
            [
                MaDecisionModel(
                    kind="sell",
                    symbol="000660",
                    decision="sell",
                    position_id=pos.id,
                    rationale="손절가 도달",
                    provisional=False,
                    created_at=T1,
                ),
                MaJournalModel(
                    position_id=pos.id,
                    one_line="갭 추격 손절",
                    lessons=["l"],
                    tags=["gap"],
                    created_at=T1,
                ),
                MaPrincipleModel(
                    condition_text="c-low",
                    action_text="a",
                    scope="buy",
                    priority="low",
                    confidence=9,
                    supporting_count=1,
                    is_active=True,
                    created_at=T1,
                    updated_at=T1,
                ),
                MaPrincipleModel(
                    condition_text="c-off",
                    action_text="a",
                    scope="buy",
                    priority="high",
                    confidence=9,
                    supporting_count=1,
                    is_active=False,
                    created_at=T1,
                    updated_at=T1,
                ),
                MaPrincipleModel(
                    condition_text="c-high",
                    action_text="a",
                    scope="all",
                    priority="high",
                    confidence=3,
                    supporting_count=2,
                    is_active=True,
                    created_at=T1,
                    updated_at=T1,
                ),
                MaMarketRegimeModel(
                    trade_date=DAY,
                    kospi_close=D("4697.51"),
                    regime="bull",
                    basis={"bars": 80},
                    created_at=T1,
                ),
                MaEquitySnapshotModel(
                    trade_date=date(2026, 11, 25),
                    realized_cum_rate=D("0"),
                    open_positions=1,
                    used_slots=D("1"),
                    created_at=T1,
                ),
                MaEquitySnapshotModel(
                    trade_date=DAY,
                    realized_cum_rate=D("-0.6"),
                    open_positions=1,
                    used_slots=D("1"),
                    kospi_cum_rate=D("1.25"),
                    created_at=T1,
                ),
            ]
        )
    return {"round": rnd.id, "report": rep.id, "position": pos.id}


async def test_dashboard_parts(factory):
    await _seed(factory)
    q = QueryRepository(factory, MagicMock())
    (trade,) = await q.closed_trades("r")
    assert trade == {
        "profit_rate": -6.0,
        "slot_weight": 1.0,
        "holding_days": 6,
        "rules": ["gap", "volume_spike"],
    }
    assert await q.open_summary("r") == {"open_positions": 1, "used_slots": 1.0}
    series = await q.equity_series(250, "r")
    assert [p["date"] for p in series] == ["2026-11-25", "2026-11-26"]
    assert series[-1]["portfolio"] == -0.6 and series[-1]["kospi"] == 1.25
    assert (await q.latest_regime("r"))["value"] == "bull"
    last = await q.last_round("r")
    assert (
        last["started_at"] == "2026-11-26T06:40:00+00:00" and last["cost_usd"] == 0.31
    )


async def test_lists_details_and_missing(factory):
    ids = await _seed(factory)
    q = QueryRepository(factory, MagicMock())
    items, total = await q.list_positions(
        status="closed", page=1, size=10, request_id="r"
    )
    assert total == 1 and items[0]["exit_reason"] == "stop"
    detail = await q.position_detail(ids["position"], "r")
    assert detail["buy_decision"]["score"] == 8 and detail["report_id"] == ids["report"]
    assert [d["decision"] for d in detail["sell_decisions"]] == ["sell"]
    assert detail["journal"]["one_line"] == "갭 추격 손절"
    assert await q.position_detail(999, "r") is None

    watch, total = await q.list_decisions(
        kind="buy", decision="skip", page=1, size=10, request_id="r"
    )
    assert total == 1 and watch[0]["skip_reason"] == "GATE: NO_SLOT"

    reports, total = await q.list_reports(
        symbol="000660", trade_date=DAY, page=1, size=10, request_id="r"
    )
    assert total == 1 and reports[0]["summary"] == "요약"
    rep = await q.report_detail(ids["report"], "r")
    assert rep["sections"][0]["role"] == "section_technical"
    assert len(rep["evidence"][0]["payload"]) == 20_000
    assert [d["decision"] for d in rep["decisions"]] == ["enter"]
    assert await q.report_detail(999, "r") is None

    rounds, total = await q.list_rounds(page=1, size=10, request_id="r")
    assert total == 1 and rounds[0]["trigger"] == "auto"
    rd = await q.round_detail(ids["round"], "r")
    assert rd["items"][0]["report_id"] == ids["report"]
    assert await q.round_detail(999, "r") is None


async def test_paging(factory):
    await _seed(factory)
    q = QueryRepository(factory, MagicMock())
    first, total = await q.list_decisions(
        kind="buy", decision=None, page=1, size=1, request_id="r"
    )
    second, _ = await q.list_decisions(
        kind="buy", decision=None, page=2, size=1, request_id="r"
    )
    assert total == 2 and first[0]["id"] != second[0]["id"]
    assert first[0]["created_at"] == "2026-11-26T06:40:00+00:00"  # 최신 먼저


async def test_insights_parts(factory):
    await _seed(factory)
    q = QueryRepository(factory, MagicMock())
    principles = await q.principles("r")
    assert [p["condition"] for p in principles] == ["c-high", "c-low", "c-off"]
    (j,) = await q.recent_journals(10, "r")
    assert (j["symbol"], j["profit_rate"], j["tags"]) == ("000660", -6.0, ["gap"])
