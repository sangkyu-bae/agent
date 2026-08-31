"""MultimodalSettingRepository 통합 테스트 (SQLite + 실제 세션).

Design §3.3 V065, FR-12.
"""

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
from src.domain.multimodal.value_objects import MultimodalSettings
from src.infrastructure.multimodal.models import (
    MULTIMODAL_SETTING_ID,
    MultimodalSettingModel,
)
from src.infrastructure.multimodal.repository import MultimodalSettingRepository
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


def _repo(session: AsyncSession) -> MultimodalSettingRepository:
    return MultimodalSettingRepository(session, MagicMock())


@pytest.mark.asyncio
async def test_get_seeds_defaults_when_row_missing(session: AsyncSession) -> None:
    """V065 시드가 없어도(신규 DB) 기본값 행을 만들어 돌려준다.

    설정 화면 첫 진입 안전.
    """
    s = await _repo(session).get("req")
    assert s.id == MULTIMODAL_SETTING_ID
    assert s.enabled is False and s.vision_model_id is None
    assert (s.max_images_per_doc, s.min_image_px, s.concurrency, s.timeout_sec) == (
        50,
        100,
        4,
        60,
    )
    assert s.min_area_ratio == pytest.approx(0.02)
    assert (s.output_language, s.detail_level) == ("ko", "detailed")


@pytest.mark.asyncio
async def test_update_replaces_all_fields_and_get_reads_back(
    session: AsyncSession,
) -> None:
    repo = _repo(session)
    current = await repo.get("req")
    new = MultimodalSettings(
        id=current.id,
        enabled=True,
        vision_model_id="model-1",
        max_images_per_doc=10,
        min_image_px=64,
        min_area_ratio=0.05,
        concurrency=2,
        timeout_sec=30,
        output_language="en",
        detail_level="brief",
        updated_at=datetime(2026, 8, 21, tzinfo=UTC),
    )
    saved = await repo.update(new, "req")
    assert saved.enabled is True and saved.vision_model_id == "model-1"
    again = await repo.get("req")
    assert again.max_images_per_doc == 10 and again.output_language == "en"
    assert again.min_area_ratio == pytest.approx(0.05)


def test_model_columns_all_have_comments() -> None:
    """CLAUDE.md §3: SQLAlchemy 모델에도 comment= 동일 반영."""
    for col in MultimodalSettingModel.__table__.columns:
        assert col.comment, f"{col.name} comment 누락"
    assert MultimodalSettingModel.__table__.comment
