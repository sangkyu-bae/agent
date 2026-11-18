"""검토 큐 API L1 — Design §4.1 review·§8.2 #10."""
from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes.admin_graph_rag_router import get_review_use_case
from src.api.routes.admin_graph_rag_router import router as admin_router
from src.application.graph_rag.admin.review_use_case import (
    GraphReviewAlreadyDoneError,
    GraphReviewNotFoundError,
    GraphReviewTargetInvalidError,
)
from src.domain.auth.entities import UserRole
from src.domain.graph_rag.resolution import ReviewStatus
from src.interfaces.dependencies.auth import get_current_user

from tests.api.test_admin_graph_rag_router import _user
from tests.application.graph_rag.test_review_use_case import _decision


def _client(uc, user=None) -> TestClient:
    app = FastAPI()
    app.include_router(admin_router)
    app.dependency_overrides[get_review_use_case] = lambda: uc
    app.dependency_overrides[get_current_user] = lambda: user or _user()
    return TestClient(app)


def test_list_pending_review():
    uc = AsyncMock()
    uc.list.return_value = ([_decision()], 1)
    r = _client(uc).get("/api/v1/admin/graph-rag/review?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["id"] == "d1" and item["decided_by"] == "llm_rejudge"
    assert item["candidates"][0]["entity_id"] == "e1"
    assert uc.list.call_args.args[0] is ReviewStatus.PENDING


def test_approve_and_reject():
    uc = AsyncMock()
    uc.reject.return_value = "e2"
    c = _client(uc)
    assert c.post("/api/v1/admin/graph-rag/review/d1/approve",
                  json={"note": "맞음"}).status_code == 204
    assert uc.approve.call_args.kwargs["reviewer"] == "99"
    r = c.post("/api/v1/admin/graph-rag/review/d1/reject",
               json={"target_entity_id": "e2", "note": "다른 상품"})
    assert r.status_code == 200 and r.json() == {"entity_id": "e2"}
    assert uc.reject.call_args.kwargs["target_entity_id"] == "e2"


def test_review_error_mapping():
    for exc, code, status_code in [
        (GraphReviewNotFoundError("x"), "GRAPH_REVIEW_NOT_FOUND", 404),
        (GraphReviewAlreadyDoneError("x"), "GRAPH_REVIEW_ALREADY_DONE", 409),
        (GraphReviewTargetInvalidError("x"), "GRAPH_REVIEW_TARGET_INVALID", 422),
    ]:
        uc = AsyncMock()
        uc.reject.side_effect = exc
        r = _client(uc).post("/api/v1/admin/graph-rag/review/d1/reject", json={})
        assert r.status_code == status_code and r.json()["detail"]["code"] == code


def test_review_forbidden_for_regular_user():
    c = _client(AsyncMock(), user=_user(UserRole.USER, 1))
    assert c.get("/api/v1/admin/graph-rag/review").status_code == 403
