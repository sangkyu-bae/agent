"""ai_answer_citation 저장소 (SQLite 실제 세션) — Design §3.3 V093."""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.domain.answer_citation.models import AnswerCitation, CitationOutcome
from src.infrastructure.answer_citation.models import AnswerCitationModel
from src.infrastructure.answer_citation.repository import (
    AnswerCitationRepository,
    SessionScopedAnswerCitationStore,
)
from src.infrastructure.persistence.models.base import Base

_CITE = AnswerCitation(
    no=1,
    marker=3,
    chunk_id="ch-3",
    document_id="d",
    page=2,
    evidence="근거 문장",
    sentence="답변 문장.",
)
VERIFIED = CitationOutcome(text="답변 문장[1].", status="verified", citations=(_CITE,))
NONE = CitationOutcome(
    text="답.", status="none", citations=(), none_reason="all_rejected"
)


@pytest.fixture
async def factory() -> AsyncGenerator[async_sessionmaker, None]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    async with engine.begin() as conn:
        # 다른 테스트가 등록한 FK 모델과 무관하게 이 테이블만 만든다.
        await conn.run_sync(
            lambda c: Base.metadata.create_all(
                c, tables=[AnswerCitationModel.__table__]
            )
        )
    try:
        yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    finally:
        await engine.dispose()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_save_and_find_roundtrip(factory):
    async with factory() as s:
        repo = AnswerCitationRepository(s, MagicMock())
        await repo.save("run-1", VERIFIED, judge_model="gpt-4o", request_id="r")
        await repo.save("run-2", NONE, judge_model=None, request_id="r")
        await s.commit()
    async with factory() as s:
        found = await AnswerCitationRepository(s, MagicMock()).find_by_runs(
            ["run-1", "run-2", "run-x"], "r"
        )
    assert set(found) == {"run-1", "run-2"}
    assert found["run-1"].status == "verified"
    assert found["run-1"].citations == (_CITE,)
    assert (found["run-2"].status, found["run-2"].none_reason) == (
        "none",
        "all_rejected",
    )


@pytest.mark.asyncio
async def test_save_overwrites_same_run(factory):
    async with factory() as s:
        repo = AnswerCitationRepository(s, MagicMock())
        await repo.save("run-1", NONE, judge_model=None, request_id="r")
        await repo.save("run-1", VERIFIED, judge_model=None, request_id="r")
        await s.commit()
        found = await repo.find_by_runs(["run-1"], "r")
    assert found["run-1"].status == "verified"


@pytest.mark.asyncio
async def test_empty_run_ids(factory):
    async with factory() as s:
        assert (
            await AnswerCitationRepository(s, MagicMock()).find_by_runs([], "r") == {}
        )


@pytest.mark.asyncio
async def test_session_scoped_store_commits(factory):
    store = SessionScopedAnswerCitationStore(factory, MagicMock())
    await store.save("run-9", VERIFIED, judge_model=None, request_id="r")
    found = await store.find_by_runs(["run-9"], "r")
    assert found["run-9"].citations[0].evidence == "근거 문장"
