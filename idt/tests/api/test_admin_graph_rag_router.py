"""admin_graph_rag_router·graph_rag_router L1 — Design §4.1·§8.2 #1~#6."""
from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from src.api.routes.admin_graph_rag_router import (
    get_change_stage_use_case,
    get_graph_health_use_case,
    get_graph_rag_settings_use_case,
)
from src.api.routes.admin_graph_rag_router import router as admin_router
from src.api.routes.graph_rag_router import get_graph_settings_reader
from src.api.routes.graph_rag_router import router as public_router
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.graph_rag.exceptions import GraphStageEvalRequiredError
from src.domain.graph_rag.value_objects import (
    GraphHealth,
    GraphRagSettings,
    RolloutStage,
    StageChange,
)
from src.interfaces.dependencies.auth import get_current_user

from tests.application.graph_rag.fakes import FakeReader


def _user(role=UserRole.ADMIN, uid=99) -> User:
    return User(
        email="a@test.com", password_hash="h", role=role,
        status=UserStatus.APPROVED, id=uid,
    )


def _client(*, user: User | None = None, settings_uc=None, stage_uc=None,
            health_uc=None, reader=None) -> TestClient:
    app = FastAPI()
    app.include_router(admin_router)
    app.include_router(public_router)
    app.dependency_overrides[get_graph_rag_settings_use_case] = lambda: settings_uc
    app.dependency_overrides[get_change_stage_use_case] = lambda: stage_uc
    app.dependency_overrides[get_graph_health_use_case] = lambda: health_uc
    app.dependency_overrides[get_graph_settings_reader] = lambda: reader
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    else:
        def _unauth():
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "no token")
        app.dependency_overrides[get_current_user] = _unauth
    return TestClient(app)


def _settings_body(**over) -> dict:
    s = GraphRagSettings.defaults()
    body = {
        "extraction_enabled": s.extraction_enabled, "jev_enabled": s.jev_enabled,
        "link_threshold": s.link_threshold, "new_threshold": s.new_threshold,
        "extraction_llm_model_id": None, "rejudge_llm_model_id": None,
        "concurrency": s.concurrency, "max_llm_calls_per_doc": s.max_llm_calls_per_doc,
        "candidate_top_k": s.candidate_top_k, "max_hops": s.max_hops,
        "graph_rrf_weight": s.graph_rrf_weight,
        "retrieval_timeout_ms": s.retrieval_timeout_ms,
        "entity_types": list(s.entity_types), "relation_types": list(s.relation_types),
    }
    body.update(over)
    return body


# ── auth ────────────────────────────────────────────────────────────────────

def test_admin_routes_forbid_regular_user():
    c = _client(user=_user(UserRole.USER, 1), settings_uc=AsyncMock())
    assert c.get("/api/v1/admin/graph-rag/settings").status_code == 403
    assert c.get("/api/v1/admin/graph-rag/health").status_code == 403
    assert c.post(
        "/api/v1/admin/graph-rag/stage", json={"to_stage": "admin_only"}
    ).status_code == 403


def test_admin_routes_require_login():
    assert _client().get("/api/v1/admin/graph-rag/settings").status_code == 401


# ── settings ────────────────────────────────────────────────────────────────

def test_get_settings_ok():
    uc = AsyncMock()
    uc.get.return_value = GraphRagSettings.defaults()
    r = _client(user=_user(), settings_uc=uc).get("/api/v1/admin/graph-rag/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["rollout_stage"] == "off" and body["max_hops"] == 2
    assert "기타" in body["entity_types"]


def test_put_settings_passes_update_and_returns_saved():
    uc = AsyncMock()
    uc.update.return_value = dataclasses.replace(
        GraphRagSettings.defaults(), jev_enabled=True
    )
    r = _client(user=_user(), settings_uc=uc).put(
        "/api/v1/admin/graph-rag/settings", json=_settings_body(jev_enabled=True)
    )
    assert r.status_code == 200 and r.json()["jev_enabled"] is True
    upd = uc.update.call_args.args[0]
    assert upd.jev_enabled is True and isinstance(upd.entity_types, tuple)


def test_put_settings_invalid_maps_to_422_code():
    uc = AsyncMock()
    uc.update.side_effect = ValueError("thresholds must satisfy ...")
    r = _client(user=_user(), settings_uc=uc).put(
        "/api/v1/admin/graph-rag/settings", json=_settings_body()
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "GRAPH_SETTINGS_INVALID"


# ── stage ───────────────────────────────────────────────────────────────────

def test_stage_change_passes_actor_and_evidence():
    uc = AsyncMock()
    uc.change.return_value = dataclasses.replace(
        GraphRagSettings.defaults(), rollout_stage=RolloutStage.ADMIN_ONLY
    )
    r = _client(user=_user(uid=7), stage_uc=uc).post(
        "/api/v1/admin/graph-rag/stage", json={"to_stage": "admin_only"}
    )
    assert r.status_code == 200 and r.json()["rollout_stage"] == "admin_only"
    args, kwargs = uc.change.call_args
    assert args[0] is RolloutStage.ADMIN_ONLY and kwargs["actor_id"] == "7"


def test_stage_general_without_evidence_409():
    uc = AsyncMock()
    uc.change.side_effect = GraphStageEvalRequiredError("need evidence")
    r = _client(user=_user(), stage_uc=uc).post(
        "/api/v1/admin/graph-rag/stage", json={"to_stage": "general"}
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "GRAPH_STAGE_EVAL_REQUIRED"


def test_stage_unknown_value_422():
    r = _client(user=_user(), stage_uc=AsyncMock()).post(
        "/api/v1/admin/graph-rag/stage", json={"to_stage": "public"}
    )
    assert r.status_code == 422


def test_stage_history_lists_items():
    uc = AsyncMock()
    uc.history.return_value = [StageChange(
        id="c1", from_stage=RolloutStage.OFF, to_stage=RolloutStage.ADMIN_ONLY,
        changed_by="99", eval_baseline_run_id=None, eval_graph_run_id=None,
        force_reason=None, created_at=datetime(2026, 11, 17, tzinfo=UTC),
    )]
    r = _client(user=_user(), stage_uc=uc).get("/api/v1/admin/graph-rag/stage-history")
    assert r.status_code == 200
    assert r.json()["items"][0]["to_stage"] == "admin_only"


# ── health ──────────────────────────────────────────────────────────────────

def test_health_reports_external_and_counts():
    uc = AsyncMock()
    uc.execute.return_value = GraphHealth(
        backend="neo4j", connected=True, external=True, node_count=3,
        relationship_count=4, node_limit=200000, relationship_limit=400000,
    )
    r = _client(user=_user(), health_uc=uc).get("/api/v1/admin/graph-rag/health")
    assert r.status_code == 200
    assert r.json() == {
        "backend": "neo4j", "connected": True, "external": True,
        "node_count": 3, "relationship_count": 4,
        "node_limit": 200000, "relationship_limit": 400000, "error": None,
    }


# ── capabilities (FR-24) ────────────────────────────────────────────────────

def test_capabilities_user_admin_only_hidden_without_stage_key():
    reader = FakeReader().with_stage(RolloutStage.ADMIN_ONLY)
    r = _client(user=_user(UserRole.USER, 1), reader=reader).get(
        "/api/v1/graph-rag/capabilities"
    )
    assert r.status_code == 200 and r.json() == {"visible": False}


def test_capabilities_admin_sees_stage():
    reader = FakeReader().with_stage(RolloutStage.ADMIN_ONLY)
    r = _client(user=_user(), reader=reader).get("/api/v1/graph-rag/capabilities")
    assert r.json() == {"visible": True, "stage": "admin_only"}


def test_capabilities_requires_login():
    assert _client(reader=FakeReader()).get(
        "/api/v1/graph-rag/capabilities"
    ).status_code == 401
