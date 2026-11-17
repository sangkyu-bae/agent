"""주제 저장소(V090·V091) — SQLite 실세션 통합 테스트."""
from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.domain.graph_rag.exceptions import GraphTopicDuplicateError
from src.domain.graph_rag.topic import (
    DocumentTopic,
    Topic,
    TopicLevel,
    TopicOrigin,
    TopicStatus,
)
from src.infrastructure.graph_rag.topic_store import (
    SessionScopedDocumentTopicStore,
    SessionScopedTopicRepository,
)
from src.infrastructure.persistence.models.base import Base


@pytest.fixture
async def factory():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    finally:
        await engine.dispose()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _t(id_, name, level=TopicLevel.MAJOR, parent=None, status=TopicStatus.ACTIVE):
    return Topic(id_, name, name.casefold(), level, parent, f"{name} 설명", status,
                 TopicOrigin.ADMIN, created_by="admin")


@pytest.mark.asyncio
async def test_topic_crud_and_filters(factory):
    repo = SessionScopedTopicRepository(factory, MagicMock())
    await repo.create(_t("t1", "여신"), "r")
    await repo.create(_t("t2", "기업여신", TopicLevel.MINOR, "t1"), "r")
    await repo.create(_t("t3", "옛것", status=TopicStatus.RETIRED), "r")

    got = await repo.get("t2", "r")
    assert (got.level, got.parent_id, got.origin, got.created_by) == (
        TopicLevel.MINOR, "t1", TopicOrigin.ADMIN, "admin")
    majors = await repo.list("r", level=TopicLevel.MAJOR, parent_id=None)
    assert [t.id for t in majors] == ["t1"]
    minors = await repo.list("r", level=TopicLevel.MINOR, parent_id="t1")
    assert [t.id for t in minors] == ["t2"]
    assert {t.id for t in await repo.list("r", include_retired=True)} == {"t1", "t2", "t3"}
    assert (await repo.find_by_name("t1", "기업여신", "r")).id == "t2"
    assert await repo.find_by_name("", "기업여신", "r") is None


@pytest.mark.asyncio
async def test_duplicate_name_under_same_parent_raises(factory):
    repo = SessionScopedTopicRepository(factory, MagicMock())
    await repo.create(_t("t1", "여신"), "r")
    with pytest.raises(GraphTopicDuplicateError):
        await repo.create(_t("t9", "여신"), "r")
    # 다른 상위 아래라면 같은 이름도 허용
    await repo.create(_t("t2", "기업", TopicLevel.MINOR, "t1"), "r")
    await repo.create(_t("t3", "기업"), "r")


@pytest.mark.asyncio
async def test_update_changes_fields_and_detects_rename_conflict(factory):
    repo = SessionScopedTopicRepository(factory, MagicMock())
    await repo.create(_t("t1", "여신"), "r")
    await repo.create(_t("t2", "수신"), "r")
    t1 = await repo.get("t1", "r")
    import dataclasses

    updated = await repo.update(
        dataclasses.replace(t1, name="여신업무", normalized_name="여신업무",
                            status=TopicStatus.RETIRED), "r")
    assert (updated.name, updated.status) == ("여신업무", TopicStatus.RETIRED)
    with pytest.raises(GraphTopicDuplicateError):
        await repo.update(dataclasses.replace(updated, normalized_name="수신"), "r")


@pytest.mark.asyncio
async def test_document_topics_replace_move_and_count(factory):
    links = SessionScopedDocumentTopicStore(factory, MagicMock())
    await links.replace("doc-1", [
        DocumentTopic("doc-1", "t1", True, 0.93, "d-major"),
        DocumentTopic("doc-1", "t2", False, None, "d-sec"),
    ], "r")
    await links.replace("doc-2", [DocumentTopic("doc-2", "t1", True, None, "d-x")], "r")
    got = await links.list_for_document("doc-1", "r")
    assert [(lk.topic_id, lk.is_primary, lk.probability) for lk in got] == [
        ("t1", True, pytest.approx(0.93)), ("t2", False, None)]
    assert await links.count_documents(["t1", "t2", "t9"], "r") == {
        "t1": 2, "t2": 1, "t9": 0}

    # 재분류는 통째로 교체
    await links.replace("doc-1", [DocumentTopic("doc-1", "t3", True, None, "d-major")], "r")
    assert [lk.topic_id for lk in await links.list_for_document("doc-1", "r")] == ["t3"]

    # 검토 거절: 판정 하나의 연결을 옮긴다
    assert await links.move("d-major", "t4", "r") == "doc-1"
    assert [lk.topic_id for lk in await links.list_for_document("doc-1", "r")] == ["t4"]
    assert await links.move("missing", "t4", "r") is None


@pytest.mark.asyncio
async def test_move_onto_already_linked_topic_merges(factory):
    links = SessionScopedDocumentTopicStore(factory, MagicMock())
    await links.replace("doc-1", [
        DocumentTopic("doc-1", "t1", True, None, "d-major"),
        DocumentTopic("doc-1", "t2", False, None, "d-sec"),
    ], "r")
    # 보조 주제 판정을 이미 대표인 t1 으로 옮기면 중복 행 대신 하나만 남긴다
    assert await links.move("d-sec", "t1", "r") == "doc-1"
    got = await links.list_for_document("doc-1", "r")
    assert [(lk.topic_id, lk.is_primary) for lk in got] == [("t1", True)]
