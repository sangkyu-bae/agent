"""주제 목록 API L1 — Design §11.9 (module-4b)."""
from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.admin_graph_rag_router import (
    get_review_use_case,
    get_topics_use_case,
)
from src.api.routes.admin_graph_rag_router import router as admin_router
from src.domain.auth.entities import UserRole
from src.domain.graph_rag.exceptions import (
    GraphTopicDuplicateError,
    GraphTopicInvalidError,
    GraphTopicNotFoundError,
)
from src.domain.graph_rag.topic import Topic, TopicLevel, TopicOrigin, TopicStatus
from src.interfaces.dependencies.auth import get_current_user

from tests.api.test_admin_graph_rag_router import _user
from tests.application.graph_rag.test_review_use_case import _decision

_BASE = "/api/v1/admin/graph-rag"


def _topic(id_="t1", name="여신", level=TopicLevel.MAJOR, parent=None):
    return Topic(id_, name, name, level, parent, "대출 업무", TopicStatus.ACTIVE,
                 TopicOrigin.ADMIN, created_by="99")


def _client(uc, user=None, review=None) -> TestClient:
    app = FastAPI()
    app.include_router(admin_router)
    app.dependency_overrides[get_topics_use_case] = lambda: uc
    if review is not None:
        app.dependency_overrides[get_review_use_case] = lambda: review
    app.dependency_overrides[get_current_user] = lambda: user or _user()
    return TestClient(app)


def test_list_topics_with_counts():
    uc = AsyncMock()
    uc.list.return_value = [(_topic(), 3),
                            (_topic("t2", "기업여신", TopicLevel.MINOR, "t1"), 1)]
    r = _client(uc).get(f"{_BASE}/topics?include_retired=true")
    assert r.status_code == 200
    items = r.json()["items"]
    assert [(i["id"], i["level"], i["parent_id"], i["document_count"]) for i in items] == [
        ("t1", 1, None, 3), ("t2", 2, "t1", 1)]
    assert items[0]["status"] == "active" and items[0]["origin"] == "admin"
    assert uc.list.call_args.kwargs["include_retired"] is True


def test_create_and_update_topic():
    uc = AsyncMock()
    uc.create.return_value = _topic()
    uc.update.return_value = _topic(name="여신업무")
    c = _client(uc)
    r = c.post(f"{_BASE}/topics", json={"name": "여신", "level": 1,
                                        "description": "대출 업무"})
    assert r.status_code == 201 and r.json()["name"] == "여신"
    assert uc.create.call_args.kwargs["actor"] == "99"
    r = c.patch(f"{_BASE}/topics/t1", json={"name": "여신업무", "status": "retired"})
    assert r.status_code == 200
    assert uc.update.call_args.kwargs["status"] == "retired"


def test_topic_request_validation():
    c = _client(AsyncMock())
    assert c.post(f"{_BASE}/topics", json={"name": "", "level": 1}).status_code == 422
    assert c.post(f"{_BASE}/topics", json={"name": "a", "level": 3}).status_code == 422
    assert c.patch(f"{_BASE}/topics/t1", json={"status": "pending"}).status_code == 422


def test_topic_error_mapping():
    for exc, code, status_code in [
        (GraphTopicDuplicateError("x"), "GRAPH_TOPIC_DUPLICATE", 409),
        (GraphTopicNotFoundError("x"), "GRAPH_TOPIC_NOT_FOUND", 404),
        (GraphTopicInvalidError("x"), "GRAPH_TOPIC_INVALID", 422),
    ]:
        uc = AsyncMock()
        uc.create.side_effect = exc
        r = _client(uc).post(f"{_BASE}/topics", json={"name": "a", "level": 1})
        assert r.status_code == status_code and r.json()["detail"]["code"] == code


def test_topics_admin_only():
    r = _client(AsyncMock(), user=_user(UserRole.USER)).get(f"{_BASE}/topics")
    assert r.status_code == 403


def test_review_item_kind_marks_topic_decisions():
    import dataclasses

    review = AsyncMock()
    review.list.return_value = ([
        _decision(),
        dataclasses.replace(_decision(), id="d2", mention_type="주제:대분류"),
    ], 2)
    r = _client(AsyncMock(), review=review).get(f"{_BASE}/review")
    assert [i["kind"] for i in r.json()["items"]] == ["entity", "topic"]


def test_stage_off_list_endpoints_return_409():
    """Check G-2: 노출 단계 off 이면 주제·검토 목록도 409 GRAPH_STAGE_OFF."""
    from src.domain.graph_rag.exceptions import GraphStageOffError

    uc, review = AsyncMock(), AsyncMock()
    uc.list.side_effect = GraphStageOffError("off")
    review.list.side_effect = GraphStageOffError("off")
    client = _client(uc, review=review)
    for path in ("topics", "review"):
        r = client.get(f"{_BASE}/{path}")
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "GRAPH_STAGE_OFF"
