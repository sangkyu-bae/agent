"""graph_rag MySQL 저장소 통합 테스트 (SQLite + 실제 세션) — Design §3.3 V086·V087."""
from __future__ import annotations

import dataclasses
import os
import tempfile
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.domain.graph_rag.value_objects import (
    GraphRagSettings,
    RolloutStage,
    StageChange,
)
from src.infrastructure.graph_rag.models import GRAPH_RAG_SETTING_ID
from src.infrastructure.graph_rag.repositories import (
    GraphRagSettingRepository,
    GraphRagStageChangeRepository,
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


@pytest.mark.asyncio
async def test_get_creates_closed_defaults_when_row_missing(session):
    s = await GraphRagSettingRepository(session, MagicMock()).get("r")
    assert s.rollout_stage is RolloutStage.OFF
    assert s.entity_types == GraphRagSettings.defaults().entity_types


@pytest.mark.asyncio
async def test_update_round_trips_all_fields(session):
    repo = GraphRagSettingRepository(session, MagicMock())
    new = dataclasses.replace(
        GraphRagSettings.defaults(),
        rollout_stage=RolloutStage.ADMIN_ONLY, extraction_enabled=True,
        jev_enabled=True, link_threshold=0.85, new_threshold=0.35,
        extraction_llm_model_id="m-1", rejudge_llm_model_id="m-2",
        concurrency=4, max_llm_calls_per_doc=500, candidate_top_k=6, max_hops=3,
        graph_rrf_weight=0.4, retrieval_timeout_ms=1200,
        entity_types=("상품", "기타"), relation_types=("요건", "기타"),
    )
    await repo.update(new, "r")
    got = await repo.get("r")
    assert dataclasses.replace(got, updated_at=None) == dataclasses.replace(
        new, updated_at=None
    )
    assert got.updated_at is not None


@pytest.mark.asyncio
async def test_unknown_stage_in_db_reads_as_off(session):
    repo = GraphRagSettingRepository(session, MagicMock())
    await repo.get("r")
    from src.infrastructure.graph_rag.models import GraphRagSettingModel

    row = await session.get(GraphRagSettingModel, GRAPH_RAG_SETTING_ID)
    row.rollout_stage = "publik"  # 오타 — 닫힘으로 읽혀야 한다
    await session.flush()
    assert (await repo.get("r")).rollout_stage is RolloutStage.OFF


@pytest.mark.asyncio
async def test_stage_changes_listed_newest_first(session):
    repo = GraphRagStageChangeRepository(session, MagicMock())
    for i, (frm, to) in enumerate([
        (RolloutStage.OFF, RolloutStage.ADMIN_ONLY),
        (RolloutStage.ADMIN_ONLY, RolloutStage.GENERAL),
    ]):
        await repo.add(StageChange(
            id=f"c{i}", from_stage=frm, to_stage=to, changed_by="99",
            eval_baseline_run_id=None, eval_graph_run_id=None,
            force_reason="시연 일정상 먼저 공개" if i else None,
            created_at=datetime(2026, 11, 17, 10, i, tzinfo=UTC),
        ), "r")
    rows = await repo.list_recent(10, "r")
    assert [r.id for r in rows] == ["c1", "c0"]
    assert rows[0].to_stage is RolloutStage.GENERAL
    assert rows[0].force_reason == "시연 일정상 먼저 공개"
