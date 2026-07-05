"""WikiArticleRepository 통합 테스트 (SQLite + 실제 세션).

mock(_base_save)으로 가려지는 update INSERT 버그를 실제 세션으로 검증한다.
embedding/vector_store는 MySQL 영속만 검증하기 위해 모킹한다.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.domain.vector.entities import Document
from src.domain.vector.value_objects import DocumentId
from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus
from src.infrastructure.persistence.models.base import Base
from src.infrastructure.wiki.models import WikiArticleModel  # noqa: F401
from src.infrastructure.wiki.wiki_repository import WikiArticleRepository

NOW = datetime(2026, 6, 28)


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    url = f"sqlite+aiosqlite:///{tmp.name}"
    engine = create_async_engine(url, future=True)
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


def _repo(session) -> WikiArticleRepository:
    embedding = MagicMock()
    embedding.embed_text = AsyncMock(return_value=[0.1, 0.2, 0.3])
    vector_store = MagicMock()
    vector_store.add_documents = AsyncMock(return_value=[])
    vector_store.delete_by_ids = AsyncMock(return_value=1)
    vector_store.search_by_vector = AsyncMock(return_value=[])
    return WikiArticleRepository(
        session=session, logger=MagicMock(), embedding=embedding,
        vector_store=vector_store, collection_name="wiki_knowledge",
    )


def _article(id="w1", status=WikiStatus.DRAFT) -> WikiArticle:
    return WikiArticle(
        id=id, agent_id="agent_1", title="제목", content="본문",
        source_type=WikiSourceType.DISTILLED, source_refs=["doc:1"],
        status=status, confidence=0.7, created_at=NOW, updated_at=NOW,
    )


@pytest.mark.asyncio
async def test_save_then_find(session):
    repo = _repo(session)
    await repo.save(_article(), "r")
    fetched = await repo.find_by_id("w1", "r")
    assert fetched is not None
    assert fetched.status == WikiStatus.DRAFT
    assert fetched.source_refs == ["doc:1"]


@pytest.mark.asyncio
async def test_update_persists_status_without_duplicate_insert(session):
    """save 후 동일 PK update가 INSERT 충돌 없이 반영되어야 한다(거버넌스 쓰기)."""
    repo = _repo(session)
    article = _article(status=WikiStatus.DRAFT)
    await repo.save(article, "r")

    article.mark_approved("admin", NOW)
    await repo.update(article, "r")  # 버그 시 IntegrityError(중복 PK)

    fetched = await repo.find_by_id("w1", "r")
    assert fetched.status == WikiStatus.APPROVED
    assert fetched.reviewer_id == "admin"


@pytest.mark.asyncio
async def test_find_by_agent_status_filter(session):
    repo = _repo(session)
    await repo.save(_article("w1", WikiStatus.DRAFT), "r")
    await repo.save(_article("w2", WikiStatus.APPROVED), "r")
    approved = await repo.find_by_agent("agent_1", "r", status=WikiStatus.APPROVED)
    assert [a.id for a in approved] == ["w2"]


@pytest.mark.asyncio
async def test_delete_removes_row(session):
    repo = _repo(session)
    await repo.save(_article(), "r")
    assert await repo.delete("w1", "r") is True
    assert await repo.find_by_id("w1", "r") is None


@pytest.mark.asyncio
async def test_search_similar_hydrates_and_filters(session):
    repo = _repo(session)
    await repo.save(_article("w1", WikiStatus.DRAFT), "r")
    await repo.save(_article("w2", WikiStatus.APPROVED), "r")
    repo._vector_store.search_by_vector = AsyncMock(return_value=[
        Document(id=DocumentId("w2"), content="본문", vector=[0.1, 0.2, 0.3], metadata={}),
        Document(id=DocumentId("w1"), content="본문", vector=[0.1, 0.2, 0.3], metadata={}),
    ])
    result = await repo.search_similar("agent_1", "쿼리", top_k=5, now=NOW, request_id="r")
    assert [a.id for a in result] == ["w2"]  # draft(w1) 제외
