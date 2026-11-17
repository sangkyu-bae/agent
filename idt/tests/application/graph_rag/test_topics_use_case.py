"""관리자 주제 목록 (Design §11.9 초기 목록, FR-27)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.application.graph_rag.admin.topics_use_case import TopicsUseCase
from src.domain.graph_rag.exceptions import (
    GraphTopicDuplicateError,
    GraphTopicInvalidError,
    GraphTopicNotFoundError,
)
from src.domain.graph_rag.topic import (
    DocumentTopic,
    Topic,
    TopicLevel,
    TopicOrigin,
    TopicStatus,
)

from tests.application.graph_rag.fakes import FakeDocumentTopics, FakeTopics


def _uc(topics=()):
    repo, links = FakeTopics(topics), FakeDocumentTopics()
    return TopicsUseCase(topics=repo, document_topics=links, logger=MagicMock()), repo, links


def _major(id_="t-loan", name="여신", status=TopicStatus.ACTIVE):
    return Topic(id_, name, name, TopicLevel.MAJOR, None, "", status, TopicOrigin.ADMIN)


@pytest.mark.asyncio
async def test_create_major_and_minor_as_active_admin_topics():
    uc, repo, _ = _uc()
    major = await uc.create(name=" 여신 ", level=1, parent_id=None,
                            description="대출 업무", actor="admin", request_id="r")
    minor = await uc.create(name="기업여신", level=2, parent_id=major.id,
                            description="", actor="admin", request_id="r")
    assert (major.name, major.status, major.origin, major.created_by) == (
        "여신", TopicStatus.ACTIVE, TopicOrigin.ADMIN, "admin")
    assert minor.parent_id == major.id and minor.level is TopicLevel.MINOR


@pytest.mark.asyncio
async def test_create_rejects_duplicate_and_bad_parent():
    uc, *_ = _uc([_major()])
    with pytest.raises(GraphTopicDuplicateError):
        await uc.create(name="여신", level=1, parent_id=None, description="",
                        actor="a", request_id="r")
    with pytest.raises(GraphTopicNotFoundError):
        await uc.create(name="x", level=2, parent_id="missing", description="",
                        actor="a", request_id="r")
    with pytest.raises(GraphTopicInvalidError):
        await uc.create(name="x", level=1, parent_id="t-loan", description="",
                        actor="a", request_id="r")


@pytest.mark.asyncio
async def test_minor_parent_must_be_usable_major():
    minor = Topic("t-m", "기업여신", "기업여신", TopicLevel.MINOR, "t-loan", "",
                  TopicStatus.ACTIVE, TopicOrigin.ADMIN)
    uc, *_ = _uc([_major(), minor, _major("t-old", "옛것", TopicStatus.RETIRED)])
    with pytest.raises(GraphTopicInvalidError):
        await uc.create(name="x", level=2, parent_id="t-m", description="",
                        actor="a", request_id="r")
    with pytest.raises(GraphTopicInvalidError):
        await uc.create(name="x", level=2, parent_id="t-old", description="",
                        actor="a", request_id="r")


@pytest.mark.asyncio
async def test_update_name_description_status():
    uc, repo, _ = _uc([_major(status=TopicStatus.PENDING)])
    t = await uc.update("t-loan", name="여신업무", description="설명",
                        status="active", request_id="r")
    assert (t.name, t.normalized_name, t.description, t.status) == (
        "여신업무", "여신업무", "설명", TopicStatus.ACTIVE)
    with pytest.raises(GraphTopicInvalidError):
        await uc.update("t-loan", name=None, description=None, status="pending",
                        request_id="r")
    with pytest.raises(GraphTopicNotFoundError):
        await uc.update("nope", name="a", description=None, status=None,
                        request_id="r")


@pytest.mark.asyncio
async def test_list_returns_tree_order_with_document_counts():
    minor = Topic("t-m", "기업여신", "기업여신", TopicLevel.MINOR, "t-loan", "",
                  TopicStatus.ACTIVE, TopicOrigin.ADMIN)
    uc, _, links = _uc([_major(), minor, _major("t-old", "옛것", TopicStatus.RETIRED)])
    links.links["d1"] = [DocumentTopic("d1", "t-loan", True, None, "x"),
                         DocumentTopic("d1", "t-m", True, None, "y")]
    items = await uc.list(include_retired=False, request_id="r")
    assert [(t.id, n) for t, n in items] == [("t-loan", 1), ("t-m", 1)]
    items = await uc.list(include_retired=True, request_id="r")
    assert {t.id for t, _ in items} == {"t-loan", "t-m", "t-old"}
