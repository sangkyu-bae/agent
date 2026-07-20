"""SearchHistoryRepository 통합 테스트 (SQLite + 실제 세션).

kb-retrieval-test D6/D7: kb_id 컬럼 additive 확장 —
save(kb_id) 저장 검증(조용한 미저장 방지) + find_by_user_and_kb.
"""
from __future__ import annotations

import os
import tempfile
from typing import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.infrastructure.collection_search.models import SearchHistoryModel
from src.infrastructure.collection_search.search_history_repository import (
    SearchHistoryRepository,
)
from src.infrastructure.persistence.models.base import Base


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    url = f"sqlite+aiosqlite:///{tmp.name}"
    engine = create_async_engine(url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
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


def _repo(session: AsyncSession) -> SearchHistoryRepository:
    return SearchHistoryRepository(session, MagicMock())


async def _save(
    repo: SearchHistoryRepository,
    *,
    user_id: str = "u1",
    collection_name: str = "col-a",
    query: str = "q",
    kb_id: str | None = None,
) -> None:
    await repo.save(
        user_id=user_id,
        collection_name=collection_name,
        query=query,
        bm25_weight=0.5,
        vector_weight=0.5,
        top_k=10,
        result_count=3,
        request_id="req-1",
        kb_id=kb_id,
    )


class TestSaveKbId:
    @pytest.mark.asyncio
    async def test_save_persists_kb_id(self, session):
        repo = _repo(session)
        await _save(repo, kb_id="kb-1")

        row = (
            await session.execute(select(SearchHistoryModel))
        ).scalar_one()
        assert row.kb_id == "kb-1"

    @pytest.mark.asyncio
    async def test_save_without_kb_id_defaults_null(self, session):
        """기존 컬렉션 검색 경로 회귀: kb_id 미전달 시 NULL 저장."""
        repo = _repo(session)
        await _save(repo)

        row = (
            await session.execute(select(SearchHistoryModel))
        ).scalar_one()
        assert row.kb_id is None


class TestFindByUserAndKb:
    @pytest.mark.asyncio
    async def test_filters_by_user_and_kb(self, session):
        repo = _repo(session)
        await _save(repo, user_id="u1", kb_id="kb-1", query="mine")
        await _save(repo, user_id="u1", kb_id="kb-2", query="other-kb")
        await _save(repo, user_id="u2", kb_id="kb-1", query="other-user")
        await _save(repo, user_id="u1", kb_id=None, query="collection-only")

        entries, total = await repo.find_by_user_and_kb(
            user_id="u1", kb_id="kb-1", limit=20, offset=0, request_id="r"
        )

        assert total == 1
        assert [e.query for e in entries] == ["mine"]
        assert entries[0].kb_id == "kb-1"

    @pytest.mark.asyncio
    async def test_pagination_and_desc_order(self, session):
        repo = _repo(session)
        for i in range(3):
            await _save(repo, kb_id="kb-1", query=f"q{i}")

        entries, total = await repo.find_by_user_and_kb(
            user_id="u1", kb_id="kb-1", limit=2, offset=0, request_id="r"
        )

        assert total == 3
        assert len(entries) == 2
        # created_at desc — 동일 시각이면 id desc 보조 정렬로 최신 우선
        assert entries[0].id > entries[1].id


class TestFindByUserAndCollectionRegression:
    @pytest.mark.asyncio
    async def test_collection_query_unaffected_by_kb_rows(self, session):
        repo = _repo(session)
        await _save(repo, collection_name="col-a", kb_id="kb-1")
        await _save(repo, collection_name="col-a", kb_id=None)

        entries, total = await repo.find_by_user_and_collection(
            user_id="u1",
            collection_name="col-a",
            limit=20,
            offset=0,
            request_id="r",
        )

        assert total == 2
