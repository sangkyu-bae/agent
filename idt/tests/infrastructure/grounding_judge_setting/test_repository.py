"""grounding_judge_setting 저장소 (SQLite 실제 세션) — Design §3.3 V094."""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.domain.grounding_judge_setting.models import GroundingJudgeSetting
from src.infrastructure.grounding_judge_setting.models import (
    GROUNDING_JUDGE_SETTING_ID,
)
from src.infrastructure.grounding_judge_setting.repository import (
    GroundingJudgeSettingRepository,
)
from src.infrastructure.persistence.models.base import Base

_MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "db"
    / "migration"
    / "V094__create_grounding_judge_setting.sql"
)


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as s:
            async with s.begin():
                yield s
    finally:
        await engine.dispose()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def test_seed_id_matches_migration():
    assert GROUNDING_JUDGE_SETTING_ID in _MIGRATION.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_get_creates_empty_row_when_missing(session):
    s = await GroundingJudgeSettingRepository(session, MagicMock()).get("r")
    assert s == GroundingJudgeSetting()


@pytest.mark.asyncio
async def test_update_then_get_roundtrip(session):
    repo = GroundingJudgeSettingRepository(session, MagicMock())
    await repo.update(GroundingJudgeSetting("m-1", updated_by="7"), "r")
    assert await repo.get("r") == GroundingJudgeSetting("m-1", updated_by="7")
    await repo.update(GroundingJudgeSetting(None, updated_by="8"), "r")
    assert (await repo.get("r")).judge_llm_model_id is None
