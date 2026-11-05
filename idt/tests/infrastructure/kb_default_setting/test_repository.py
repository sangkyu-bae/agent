"""KbDefaultSettingRepository 통합 테스트 (SQLite + 실제 세션) — Design §3.3 V084."""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.domain.kb_default_setting.entities import KbDefaultSetting
from src.infrastructure.kb_default_setting.models import (
    KB_DEFAULT_SETTING_ID,
    KbDefaultSettingModel,
)
from src.infrastructure.kb_default_setting.repository import (
    KbDefaultSettingRepository,
)
from src.infrastructure.persistence.models.base import Base


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


def _repo(session: AsyncSession) -> KbDefaultSettingRepository:
    return KbDefaultSettingRepository(session, MagicMock())


@pytest.mark.asyncio
async def test_get_creates_row_when_missing(session: AsyncSession) -> None:
    s = await _repo(session).get("req")
    assert s.default_embedding_model_id is None
    assert s.configured is False
    row = await session.get(KbDefaultSettingModel, KB_DEFAULT_SETTING_ID)
    assert row is not None


@pytest.mark.asyncio
async def test_update_persists_model_id(session: AsyncSession) -> None:
    repo = _repo(session)
    await repo.get("req")
    saved = await repo.update(
        KbDefaultSetting(default_embedding_model_id=5, updated_at=datetime.now(UTC)),
        "req",
    )
    assert saved.default_embedding_model_id == 5
    again = await repo.get("req")
    assert again.default_embedding_model_id == 5
    assert again.updated_at is not None


@pytest.mark.asyncio
async def test_model_comments_match_ddl(session: AsyncSession) -> None:
    """CLAUDE.md §3: 모델 comment= 는 마이그레이션 COMMENT 와 동일."""
    assert (
        KbDefaultSettingModel.__table__.comment
        == "지식베이스 자동 구성 전역 기본값 — 단일 행"
    )
    for col in KbDefaultSettingModel.__table__.columns:
        assert col.comment, f"{col.name} comment missing"
