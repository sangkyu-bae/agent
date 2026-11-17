"""관리자 추출 잡 API L1 — Design §4.1·§4.2 extract·§8.2 #7~#9."""
from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes.admin_graph_rag_router import get_extraction_jobs_use_case
from src.api.routes.admin_graph_rag_router import router as admin_router
from src.application.graph_rag.admin.jobs_use_case import (
    DocumentJobRow,
    DocumentNotFoundError,
    GraphJobBusyError,
    GraphModelMissingError,
    GraphUnsupportedDocumentError,
)
from src.domain.auth.entities import UserRole
from src.domain.graph_rag.exceptions import (
    GraphBackendUnavailableError,
    GraphStageOffError,
)
from src.domain.graph_rag.extraction import JobMode
from src.interfaces.dependencies.auth import get_current_user

from tests.api.test_admin_graph_rag_router import _user
from tests.application.graph_rag.test_extraction_use_case import _job


def _client(uc, user=None) -> TestClient:
    app = FastAPI()
    app.include_router(admin_router)
    app.dependency_overrides[get_extraction_jobs_use_case] = lambda: uc
    app.dependency_overrides[get_current_user] = lambda: user or _user()
    return TestClient(app)


def test_extract_returns_202_with_job():
    uc = AsyncMock()
    uc.trigger.return_value = _job(JobMode.REBUILD)
    r = _client(uc).post(
        "/api/v1/admin/graph-rag/documents/doc-1/extract", json={"mode": "rebuild"}
    )
    assert r.status_code == 202
    assert r.json() == {"job_id": "j1", "status": "pending"}
    args, kwargs = uc.trigger.call_args
    assert args[:2] == ("doc-1", JobMode.REBUILD) and kwargs["actor_id"] == "99"


def test_extract_default_mode_is_resume():
    uc = AsyncMock()
    uc.trigger.return_value = _job()
    _client(uc).post("/api/v1/admin/graph-rag/documents/doc-1/extract", json={})
    assert uc.trigger.call_args.args[1] is JobMode.RESUME


def test_extract_error_mapping():
    cases = [
        (GraphStageOffError("off"), 409, "GRAPH_STAGE_OFF"),
        (GraphJobBusyError("busy"), 409, "GRAPH_JOB_BUSY"),
        (GraphModelMissingError("m"), 422, "GRAPH_EXTRACTION_MODEL_MISSING"),
        (DocumentNotFoundError("x"), 404, "DOCUMENT_NOT_FOUND"),
        (GraphBackendUnavailableError("down"), 503, "GRAPH_BACKEND_UNAVAILABLE"),
        (GraphUnsupportedDocumentError("xlsx"), 422, "GRAPH_UNSUPPORTED_DOCUMENT"),
    ]
    for exc, status_code, code in cases:
        uc = AsyncMock()
        uc.trigger.side_effect = exc
        r = _client(uc).post(
            "/api/v1/admin/graph-rag/documents/doc-1/extract", json={"mode": "resume"}
        )
        assert r.status_code == status_code, code
        assert r.json()["detail"]["code"] == code


def test_extract_invalid_mode_422():
    r = _client(AsyncMock()).post(
        "/api/v1/admin/graph-rag/documents/doc-1/extract", json={"mode": "all"}
    )
    assert r.status_code == 422


def test_job_detail_and_404():
    uc = AsyncMock()
    uc.get.return_value = _job()
    r = _client(uc).get("/api/v1/admin/graph-rag/jobs/j1")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "j1" and body["status"] == "pending"
    assert body["trigger_source"] == "admin"
    uc.get.return_value = None
    assert _client(uc).get("/api/v1/admin/graph-rag/jobs/zz").status_code == 404


def test_kb_documents_with_latest_job():
    uc = AsyncMock()
    uc.list_kb_documents.return_value = (
        [DocumentJobRow("doc-1", "a.pdf", 12, _job()),
         DocumentJobRow("doc-2", "b.pdf", 3, None)],
        2,
    )
    r = _client(uc).get("/api/v1/admin/graph-rag/kbs/kb-1/documents?limit=50")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    assert body["items"][0]["job"]["status"] == "pending"
    assert body["items"][1]["job"] is None
    assert uc.list_kb_documents.call_args.kwargs["limit"] == 50


def test_jobs_routes_forbid_regular_user():
    c = _client(AsyncMock(), user=_user(UserRole.USER, 1))
    assert c.get("/api/v1/admin/graph-rag/kbs/kb-1/documents").status_code == 403
    assert c.post(
        "/api/v1/admin/graph-rag/documents/doc-1/extract", json={}
    ).status_code == 403
