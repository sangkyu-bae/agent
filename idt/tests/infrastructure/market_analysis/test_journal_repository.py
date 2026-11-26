"""저널 · 원칙 저장소 (SQLite 실제 세션) — UNIQUE
· 합치기 · 선택 · 켜고 끄기 · 진입 되돌리기."""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncGenerator
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.domain.market_analysis.account import DecisionDraft
from src.domain.market_analysis.principle import JournalDraft, PrincipleCandidate
from src.infrastructure.market_analysis.account_repository import DecisionRepository
from src.infrastructure.market_analysis.journal_repository import (
    JournalRepository,
    PrincipleRepository,
)
from src.infrastructure.market_analysis.models import (
    MaDecisionModel,
    MaJournalModel,
    MaPositionModel,
    MaPrincipleModel,
)
from src.infrastructure.persistence.models.base import Base

D = Decimal
NOW = datetime(2026, 11, 26, 6, 40)


@pytest.fixture
async def factory() -> AsyncGenerator[async_sessionmaker, None]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    tables = [
        MaPositionModel.__table__,
        MaDecisionModel.__table__,
        MaJournalModel.__table__,
        MaPrincipleModel.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    finally:
        await engine.dispose()
        os.unlink(tmp.name)


async def _position(factory, status="closed") -> int:
    async with factory() as s, s.begin():
        row = MaPositionModel(
            symbol="000660",
            name="SK하이닉스",
            status=status,
            slot_weight=D("1"),
            entry_price=D("10000"),
            entry_at=datetime(2026, 11, 20, 1),
            target_price=D("12000"),
            stop_loss=D("9500"),
            exit_price=D("9400"),
            exit_at=NOW,
            exit_reason="stop",
            profit_rate=D("-6.0000"),
            holding_days=6,
            created_at=NOW,
            updated_at=NOW,
        )
        s.add(row)
        await s.flush()
        return int(row.id)


def _draft(pid, **kw):
    base = dict(
        position_id=pid,
        one_line="한 줄",
        situation="s",
        evaluation="e",
        lessons=("l",),
        tags=("gap",),
        raw_answer=None,
        run_id="run-1",
        created_at=NOW,
    )
    base.update(kw)
    return JournalDraft(**base)


def _cand(
    condition="갭 상승 다음 날",
    action="진입하지 않는다",
    scope="buy",
    priority="high",
    confidence=3,
):
    return PrincipleCandidate(condition, action, "근거", scope, priority, confidence)


async def test_closed_position_decisions_and_unique_journal(factory):
    pid = await _position(factory)
    decisions = DecisionRepository(factory, MagicMock())
    for kind, decision, at in (
        ("sell", "sell", NOW),
        ("buy", "enter", datetime(2026, 11, 20)),
    ):
        await decisions.add(
            DecisionDraft(
                kind=kind,
                symbol="000660",
                name=None,
                decision=decision,
                created_at=at,
                position_id=pid,
                rationale=f"{kind} 근거",
            ),
            "r",
        )
    repo = JournalRepository(factory, MagicMock())
    pos = await repo.closed_position(pid, "r")
    assert (pos.exit_price, pos.exit_reason, pos.holding_days) == (D("9400"), "stop", 6)
    history = await repo.decisions_for(pid, "r")
    assert [d.kind for d in history] == ["buy", "sell"]  # 오래된 순

    assert await repo.has_journal(pid, "r") is False
    jid = await repo.save_journal(_draft(pid), "r")
    assert jid is not None and await repo.has_journal(pid, "r") is True
    assert await repo.save_journal(_draft(pid, one_line="두 번째"), "r") is None

    open_pid = await _position(factory, status="open")
    assert await repo.closed_position(open_pid, "r") is None


async def test_candidates_merge_inactive_by_default_and_selection(factory):
    repo = PrincipleRepository(factory, MagicMock())
    ids = await repo.add_candidates(
        journal_id=1,
        candidates=[_cand(), _cand(condition="RSI 80", scope="sell")],
        auto_activate=False,
        request_id="r",
    )
    assert len(ids) == 2
    assert await repo.active(scope="buy", limit=10, request_id="r") == []  # U12 · DD9

    again = await repo.add_candidates(
        journal_id=2,
        candidates=[
            _cand(condition=" 갭 상승  다음 날", action="진입하지 않는다", confidence=7)
        ],
        auto_activate=True,
        request_id="r",
    )
    assert again == [ids[0]]  # 같은 원칙 → 새 행 없음
    async with factory() as s:
        rows = (
            (await s.execute(select(MaPrincipleModel).order_by(MaPrincipleModel.id)))
            .scalars()
            .all()
        )
    assert len(rows) == 2
    assert (rows[0].supporting_count, rows[0].confidence, rows[0].is_active) == (
        2,
        7,
        False,
    )

    assert (
        await repo.set_active(
            principle_id=ids[0],
            is_active=True,
            priority="medium",
            updated_by="3",
            request_id="r",
        )
        is True
    )
    assert (
        await repo.set_active(
            principle_id=999,
            is_active=True,
            priority=None,
            updated_by="3",
            request_id="r",
        )
        is False
    )
    (p,) = await repo.active(scope="buy", limit=10, request_id="r")
    assert p.id == ids[0] and "갭 상승 다음 날 → 진입하지 않는다" in p.text
    assert "근거 거래 2건" in p.text
    assert await repo.active(scope="sell", limit=10, request_id="r") == []


async def test_auto_activate_true_creates_active(factory):
    repo = PrincipleRepository(factory, MagicMock())
    await repo.add_candidates(
        journal_id=1,
        candidates=[_cand(scope="all")],
        auto_activate=True,
        request_id="r",
    )
    assert len(await repo.active(scope="sell", limit=10, request_id="r")) == 1


async def test_mark_entry_failed_only_reverts_enter(factory):
    decisions = DecisionRepository(factory, MagicMock())
    did = await decisions.add(
        DecisionDraft(
            kind="buy", symbol="A", name=None, decision="enter", created_at=NOW
        ),
        "r",
    )
    await decisions.mark_entry_failed(
        decision_id=did, reason="ENTRY_FAILED: x", request_id="r"
    )
    async with factory() as s:
        row = await s.get(MaDecisionModel, did)
    assert (row.decision, row.skip_reason) == ("skip", "ENTRY_FAILED: x")
