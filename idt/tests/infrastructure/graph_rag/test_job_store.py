"""SessionScopedExtractionJobStore (V088) — SQLite 실세션 통합 테스트."""
from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.domain.graph_rag.extraction import (
    ExtractionJob,
    JobCounters,
    JobMode,
    JobStatus,
    TriggerSource,
)
from src.infrastructure.graph_rag.job_store import SessionScopedExtractionJobStore
from src.infrastructure.persistence.models.base import Base


@pytest.fixture
async def store():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        yield SessionScopedExtractionJobStore(factory, MagicMock())
    finally:
        await engine.dispose()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _job(jid, doc="doc-1", status=JobStatus.PENDING) -> ExtractionJob:
    return ExtractionJob(
        id=jid, document_id=doc, kb_id="kb-1", collection_name="col",
        status=status, mode=JobMode.RESUME, trigger_source=TriggerSource.ADMIN,
        requested_by="99",
    )


@pytest.mark.asyncio
async def test_create_get_and_active(store):
    await store.create(_job("j1"), "r")
    got = await store.get("j1", "r")
    assert got.status is JobStatus.PENDING and got.trigger_source is TriggerSource.ADMIN
    assert (await store.find_active("doc-1", "r")).id == "j1"
    assert await store.find_active("doc-x", "r") is None


@pytest.mark.asyncio
async def test_progress_and_finish(store):
    await store.create(_job("j1"), "r")
    await store.mark_processing("j1", 7, "r")
    c = JobCounters(processed_chunks=3, failed_chunks=1, llm_calls=3,
                    entities_created=5, entities_linked=2, relations_created=4)
    await store.save_progress("j1", c, "r")
    got = await store.get("j1", "r")
    assert got.status is JobStatus.PROCESSING and got.total_chunks == 7
    assert (got.processed_chunks, got.relations_created) == (3, 4)
    assert got.started_at is not None
    await store.finish("j1", JobStatus.PARTIAL, c, "budget", "r")
    got = await store.get("j1", "r")
    assert got.status is JobStatus.PARTIAL and got.error_message == "budget"
    assert got.finished_at is not None
    assert await store.find_active("doc-1", "r") is None


@pytest.mark.asyncio
async def test_latest_by_documents_picks_newest(store):
    await store.create(_job("old", "d1", JobStatus.COMPLETED), "r")
    await store.create(_job("new", "d1"), "r")
    await store.create(_job("other", "d2"), "r")
    latest = await store.latest_by_documents(["d1", "d2", "d3"], "r")
    assert latest["d1"].id == "new" and latest["d2"].id == "other"
    assert "d3" not in latest


@pytest.mark.asyncio
async def test_fail_interrupted(store):
    await store.create(_job("a", "d1"), "r")
    await store.create(_job("b", "d2"), "r")
    await store.mark_processing("b", 3, "r")
    await store.create(_job("c", "d3", JobStatus.COMPLETED), "r")
    assert await store.fail_interrupted("r") == 2
    assert (await store.get("a", "r")).status is JobStatus.FAILED
    assert (await store.get("b", "r")).error_message == "interrupted"
    assert (await store.get("c", "r")).status is JobStatus.COMPLETED
