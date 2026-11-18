"""SessionScopedDecisionStore (V089) — SQLite 실세션 통합 테스트."""
from __future__ import annotations

import dataclasses
import os
import tempfile
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.domain.graph_rag.resolution import (
    DecidedBy,
    LlmConfidence,
    ResolutionBand,
    ResolutionDecision,
    ReviewStatus,
)
from src.infrastructure.graph_rag.decision_store import SessionScopedDecisionStore
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
        yield SessionScopedDecisionStore(factory, MagicMock())
    finally:
        await engine.dispose()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _d(did="d1", status=ReviewStatus.PENDING, **over):
    base = ResolutionDecision(
        id=did, job_id="j1", document_id="doc", chunk_id="p1", mention_text="A 상품",
        mention_type="상품",
        candidates=({"label": "C1", "entity_id": "e1", "name": "A상품", "type": "상품",
                     "match": "vector", "similarity": 0.91},),
        probabilities={"C1": 0.6, "NEW": 0.4}, chosen_label="C1", entity_id="e1",
        created_new=False, decided_by=DecidedBy.LLM_REJUDGE, band=ResolutionBand.REJUDGE,
        probability=0.6, llm_confidence=LlmConfidence.MEDIUM, llm_reason="같은 상품",
        review_status=status,
    )
    return dataclasses.replace(base, **over)


@pytest.mark.asyncio
async def test_upsert_round_trip_and_overwrite(store):
    await store.upsert_many([_d()], "r")
    got = await store.get("d1", "r")
    assert got.candidates[0]["entity_id"] == "e1"
    assert got.probabilities == {"C1": 0.6, "NEW": 0.4}
    assert got.decided_by is DecidedBy.LLM_REJUDGE and got.band is ResolutionBand.REJUDGE
    assert got.llm_confidence is LlmConfidence.MEDIUM and got.probability == 0.6
    # 재실행 — 같은 id 는 덮어쓴다(중복 행 없음)
    await store.upsert_many([_d(entity_id="e9", chosen_label="NEW")], "r")
    got = await store.get("d1", "r")
    assert got.entity_id == "e9"
    items, total = await store.list_by_review_status(ReviewStatus.PENDING, 10, 0, "r")
    assert total == 1


@pytest.mark.asyncio
async def test_rerun_does_not_reopen_reviewed_decision(store):
    await store.upsert_many([_d()], "r")
    await store.mark_reviewed("d1", ReviewStatus.APPROVED, "99", "ok", "e1", "r")
    await store.upsert_many([_d()], "r")  # 같은 청크 재추출
    got = await store.get("d1", "r")
    assert got.review_status is ReviewStatus.APPROVED and got.reviewed_by == "99"


@pytest.mark.asyncio
async def test_list_by_status_paginates(store):
    await store.upsert_many(
        [_d(f"d{i}") for i in range(5)] + [_d("x", ReviewStatus.NONE)], "r"
    )
    items, total = await store.list_by_review_status(ReviewStatus.PENDING, 2, 2, "r")
    assert total == 5 and len(items) == 2


@pytest.mark.asyncio
async def test_mark_reviewed_sets_reviewer_and_entity(store):
    await store.upsert_many([_d()], "r")
    await store.mark_reviewed("d1", ReviewStatus.REJECTED, "99", "다름", "e7", "r")
    got = await store.get("d1", "r")
    assert got.review_status is ReviewStatus.REJECTED
    assert (got.reviewed_by, got.review_note, got.entity_id) == ("99", "다름", "e7")
    assert got.reviewed_at is not None


@pytest.mark.asyncio
async def test_delete_for_document_removes_only_that_document(store):
    """Check M-1: 지운 문서의 판정이 검토 큐에 남지 않게."""
    await store.upsert_many([_d("d1"), _d("d2"), _d("d3", document_id="other")], "r")
    assert await store.delete_for_document("doc", "r") == 2
    items, total = await store.list_by_review_status(ReviewStatus.PENDING, 10, 0, "r")
    assert total == 1 and items[0].id == "d3"
