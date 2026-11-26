"""모듈 설정 저장소 (SQLite 실제 세션) —
stock-analysis-agents design §3.3 ma_setting."""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncGenerator
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.infrastructure.market_analysis.models import MaSettingModel
from src.infrastructure.market_analysis.repositories import SettingRepository
from src.infrastructure.persistence.models.base import Base


@pytest.fixture
async def factory() -> AsyncGenerator[async_sessionmaker, None]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(c, tables=[MaSettingModel.__table__])
        )
    try:
        yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    finally:
        await engine.dispose()
        os.unlink(tmp.name)


async def test_missing_row_returns_defaults(factory):
    async with factory() as session:
        repo = SettingRepository(session, MagicMock())
        assert await repo.get("r") == MarketAnalysisSetting.defaults()


async def test_reads_stored_row(factory):
    async with factory() as session:
        session.add(
            MaSettingModel(
                id=1,
                enabled=True,
                round_times=["09:30", "18:10"],
                max_per_round=5,
                max_per_day=12,
                max_concurrent_stocks=1,
                max_concurrent_runs=2,
                signal_rules=["volume_spike"],
                rule_params={"volume_spike": {"ratio": 3}},
                ranking_kinds=["volume"],
                ranking_limit=20,
                condition_seqs=["0"],
                intraday_entry_allowed=False,
                slot_count=8,
                min_score_by_regime={
                    "strong_bull": 4,
                    "bull": 5,
                    "neutral": 6,
                    "bear": 7,
                    "strong_bear": 9,
                },
                min_rr=Decimal("1.50"),
                max_stop_pct=Decimal("6.00"),
                min_stop_pct=Decimal("1.00"),
                max_principles=5,
                principle_auto_activate=True,
                run_as_user_id="7",
                kis_server_id="kis-1",
                dart_server_id=None,
                perplexity_server_id="pplx-1",
                updated_by="7",
                updated_at=datetime(2026, 11, 26, 1, 0, 0),
            )
        )
        await session.commit()

    async with factory() as session:
        s = await SettingRepository(session, MagicMock()).get("r")
    assert s.enabled is True
    assert s.round_times == ("09:30", "18:10")
    assert (s.max_per_round, s.max_per_day, s.slot_count) == (5, 12, 8)
    assert s.signal_rules == ("volume_spike",)
    assert s.rule_params == {"volume_spike": {"ratio": 3}}
    assert s.condition_seqs == ("0",)
    assert s.min_score_by_regime["strong_bear"] == 9
    assert s.min_rr == Decimal("1.50")
    assert s.principle_auto_activate is True
    assert (s.run_as_user_id, s.kis_server_id, s.dart_server_id) == ("7", "kis-1", None)
