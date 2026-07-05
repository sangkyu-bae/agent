"""API 테스트: WikiRouter (distill/목록/상세/승인/반려/폐기/복구/편집)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.wiki_router import (
    router,
    get_distill_use_case,
    get_query_use_case,
    get_review_use_case,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus
from src.interfaces.dependencies.auth import get_current_user

NOW = datetime(2026, 6, 28)


def _user(role="admin") -> User:
    return User(
        email="admin@example.com", password_hash="hashed",
        role=UserRole(role), status=UserStatus.APPROVED, id=1,
    )


def _entity(id="w1", status=WikiStatus.DRAFT) -> WikiArticle:
    return WikiArticle(
        id=id, agent_id="agent_1", title="제목", content="본문",
        source_type=WikiSourceType.DISTILLED, source_refs=["doc:1"],
        status=status, confidence=0.7, version=1, created_at=NOW, updated_at=NOW,
    )


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(router)
    return a


@pytest.fixture
def distill_uc():
    uc = MagicMock()
    uc.execute = AsyncMock(return_value=[_entity("w1"), _entity("w2")])
    return uc


@pytest.fixture
def query_uc():
    uc = MagicMock()
    uc.list_by_agent = AsyncMock(return_value=[_entity("w1", WikiStatus.APPROVED)])
    uc.get_by_id = AsyncMock(return_value=_entity("w1"))
    return uc


@pytest.fixture
def review_uc():
    uc = MagicMock()
    uc.approve = AsyncMock(return_value=_entity("w1", WikiStatus.APPROVED))
    uc.reject = AsyncMock(return_value=_entity("w1", WikiStatus.DEPRECATED))
    uc.deprecate = AsyncMock(return_value=_entity("w1", WikiStatus.DEPRECATED))
    uc.restore = AsyncMock(return_value=_entity("w1", WikiStatus.APPROVED))
    uc.edit = AsyncMock(return_value=_entity("w1"))
    return uc


@pytest.fixture
def client(app, distill_uc, query_uc, review_uc):
    app.dependency_overrides[get_distill_use_case] = lambda: distill_uc
    app.dependency_overrides[get_query_use_case] = lambda: query_uc
    app.dependency_overrides[get_review_use_case] = lambda: review_uc
    app.dependency_overrides[get_current_user] = lambda: _user("admin")
    return TestClient(app)


class TestDistill:

    def test_distill_returns_count_and_items(self, client):
        r = client.post("/api/v1/wiki/distill", json={
            "agent_id": "agent_1", "collection_name": "policy", "max_articles": 10,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["created_count"] == 2
        assert len(body["items"]) == 2
        assert body["items"][0]["status"] == "draft"

    def test_distill_value_error_422(self, app):
        uc = MagicMock()
        uc.execute = AsyncMock(side_effect=ValueError("bad"))
        app.dependency_overrides[get_distill_use_case] = lambda: uc
        app.dependency_overrides[get_current_user] = lambda: _user("admin")
        c = TestClient(app)
        r = c.post("/api/v1/wiki/distill", json={
            "agent_id": "a", "collection_name": "c",
        })
        assert r.status_code == 422


class TestList:

    def test_list_requires_agent_id(self, client):
        r = client.get("/api/v1/wiki")
        assert r.status_code == 422  # agent_id 필수

    def test_list_returns_items(self, client):
        r = client.get("/api/v1/wiki?agent_id=agent_1&status=approved")
        assert r.status_code == 200
        assert r.json()["total"] == 1

    def test_list_invalid_status_422(self, client):
        r = client.get("/api/v1/wiki?agent_id=agent_1&status=bogus")
        assert r.status_code == 422


class TestGet:

    def test_get_by_id(self, client):
        r = client.get("/api/v1/wiki/w1")
        assert r.status_code == 200
        assert r.json()["id"] == "w1"

    def test_get_404(self, app, distill_uc, review_uc):
        uc = MagicMock()
        uc.get_by_id = AsyncMock(return_value=None)
        app.dependency_overrides[get_query_use_case] = lambda: uc
        app.dependency_overrides[get_current_user] = lambda: _user("admin")
        c = TestClient(app)
        assert c.get("/api/v1/wiki/missing").status_code == 404


class TestReviewActions:

    def test_approve(self, client):
        r = client.patch("/api/v1/wiki/w1/approve", json={"reviewer_id": "admin"})
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

    def test_reject(self, client):
        r = client.patch("/api/v1/wiki/w1/reject")
        assert r.status_code == 200
        assert r.json()["status"] == "deprecated"

    def test_deprecate(self, client):
        r = client.patch("/api/v1/wiki/w1/deprecate")
        assert r.status_code == 200
        assert r.json()["status"] == "deprecated"

    def test_restore(self, client):
        r = client.patch("/api/v1/wiki/w1/restore", json={"reviewer_id": "admin"})
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

    def test_edit(self, client):
        r = client.put("/api/v1/wiki/w1", json={
            "title": "x", "content": "y", "editor_id": "admin",
        })
        assert r.status_code == 200

    def test_approve_invalid_transition_422(self, app, distill_uc, query_uc):
        uc = MagicMock()
        uc.approve = AsyncMock(side_effect=ValueError("허용되지 않은 상태 전이"))
        app.dependency_overrides[get_review_use_case] = lambda: uc
        app.dependency_overrides[get_current_user] = lambda: _user("admin")
        c = TestClient(app)
        r = c.patch("/api/v1/wiki/w1/approve", json={"reviewer_id": "admin"})
        assert r.status_code == 422

    def test_approve_not_found_404(self, app, distill_uc, query_uc):
        uc = MagicMock()
        uc.approve = AsyncMock(side_effect=ValueError("위키 항목을 찾을 수 없습니다: w1"))
        app.dependency_overrides[get_review_use_case] = lambda: uc
        app.dependency_overrides[get_current_user] = lambda: _user("admin")
        c = TestClient(app)
        r = c.patch("/api/v1/wiki/w1/approve", json={"reviewer_id": "admin"})
        assert r.status_code == 404

    def test_approve_forbidden_for_non_admin(self, client, app):
        app.dependency_overrides[get_current_user] = lambda: _user("user")
        r = client.patch("/api/v1/wiki/w1/approve", json={"reviewer_id": "admin"})
        assert r.status_code == 403
