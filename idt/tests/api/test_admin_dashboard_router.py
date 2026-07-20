"""admin-dashboard 라우터 테스트 — 401/403/200 + 스키마 계약 (Design §5.2)."""
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.domain.admin_dashboard.schemas import (
    ChunkStats,
    DashboardStats,
    DocumentStats,
    HealthComponent,
    KbBreakdownRow,
    KbStats,
    RecentDocumentRow,
    UserStats,
)
from src.domain.auth.entities import User, UserRole, UserStatus


def _make_user(role: UserRole) -> User:
    return User(
        email="test@example.com",
        password_hash="hash",
        role=role,
        status=UserStatus.APPROVED,
        id=1,
    )


def _make_stats() -> DashboardStats:
    return DashboardStats(
        kb=KbStats(total=3, active=2, by_scope={"PERSONAL": 1, "PUBLIC": 2}),
        documents=DocumentStats(total=10, with_kb=8, without_kb=2),
        chunks=ChunkStats(total=120),
        users=UserStats(total=5, approved=4, pending=1, admins=1),
    )


def _build_client(role: UserRole = UserRole.ADMIN):
    from src.api.routes.admin_dashboard_router import (
        get_dashboard_stats_use_case,
        get_kb_breakdown_use_case,
        get_recent_documents_use_case,
        get_storage_health_use_case,
        router,
    )
    from src.interfaces.dependencies.auth import get_current_user

    app = FastAPI()
    app.include_router(router)

    stats_uc = AsyncMock()
    stats_uc.execute.return_value = _make_stats()
    breakdown_uc = AsyncMock()
    breakdown_uc.execute.return_value = [
        KbBreakdownRow(
            kb_id="kb-1", name="규정집", scope="PUBLIC", status="active",
            document_count=5, chunk_count=100,
            last_uploaded_at=datetime(2026, 7, 17, 9, 0),
        ),
        KbBreakdownRow(
            kb_id="kb-2", name="빈 KB", scope="PERSONAL", status="active",
            document_count=0, chunk_count=0, last_uploaded_at=None,
        ),
    ]
    recent_uc = AsyncMock()
    recent_uc.execute.return_value = [
        RecentDocumentRow(
            document_id="d1", filename="a.pdf", kb_id="kb-1", kb_name="규정집",
            collection_name="col", chunk_count=3, chunk_strategy="parent_child",
            created_at=datetime(2026, 7, 18, 8, 0),
        ),
    ]
    health_uc = AsyncMock()
    health_uc.execute.return_value = [
        HealthComponent(name="mysql", status="ok", latency_ms=4, error=None),
        HealthComponent(
            name="elasticsearch", status="fail", latency_ms=None, error="timeout(3s)"
        ),
    ]

    app.dependency_overrides[get_current_user] = lambda: _make_user(role)
    app.dependency_overrides[get_dashboard_stats_use_case] = lambda: stats_uc
    app.dependency_overrides[get_kb_breakdown_use_case] = lambda: breakdown_uc
    app.dependency_overrides[get_recent_documents_use_case] = lambda: recent_uc
    app.dependency_overrides[get_storage_health_use_case] = lambda: health_uc

    return TestClient(app), {
        "stats": stats_uc,
        "breakdown": breakdown_uc,
        "recent": recent_uc,
        "health": health_uc,
    }


ENDPOINTS = [
    "/api/v1/admin/dashboard/stats",
    "/api/v1/admin/dashboard/kb-breakdown",
    "/api/v1/admin/dashboard/recent-documents",
    "/api/v1/admin/dashboard/health",
]


class TestAuth:
    @pytest.mark.parametrize("path", ENDPOINTS)
    def test_non_admin_gets_403(self, path):
        client, _ = _build_client(role=UserRole.USER)
        assert client.get(path).status_code == 403

    @pytest.mark.parametrize("path", ENDPOINTS)
    def test_unauthenticated_gets_401(self, path):
        from src.api.routes.admin_dashboard_router import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        assert client.get(path).status_code == 401


class TestStats:
    def test_returns_stats_schema(self):
        client, _ = _build_client()
        res = client.get("/api/v1/admin/dashboard/stats")
        assert res.status_code == 200
        body = res.json()
        assert body["kb"]["total"] == 3
        assert body["kb"]["by_scope"]["PUBLIC"] == 2
        assert body["documents"]["without_kb"] == 2
        assert body["chunks"]["total"] == 120
        assert body["users"]["admins"] == 1


class TestKbBreakdown:
    def test_returns_rows_with_empty_kb(self):
        client, _ = _build_client()
        res = client.get("/api/v1/admin/dashboard/kb-breakdown")
        assert res.status_code == 200
        rows = res.json()["rows"]
        assert len(rows) == 2
        assert rows[1]["document_count"] == 0
        assert rows[1]["last_uploaded_at"] is None


class TestRecentDocuments:
    def test_default_limit_passed(self):
        client, mocks = _build_client()
        res = client.get("/api/v1/admin/dashboard/recent-documents")
        assert res.status_code == 200
        _, kwargs = mocks["recent"].execute.await_args
        assert kwargs["limit"] == 10
        assert res.json()["rows"][0]["kb_name"] == "규정집"

    @pytest.mark.parametrize("limit", [0, 51])
    def test_limit_out_of_range_422(self, limit):
        client, _ = _build_client()
        res = client.get(
            f"/api/v1/admin/dashboard/recent-documents?limit={limit}"
        )
        assert res.status_code == 422


class TestHealth:
    def test_partial_failure_still_200(self):
        client, _ = _build_client()
        res = client.get("/api/v1/admin/dashboard/health")
        assert res.status_code == 200
        components = res.json()["components"]
        by_name = {c["name"]: c for c in components}
        assert by_name["mysql"]["status"] == "ok"
        assert by_name["elasticsearch"]["status"] == "fail"
        assert by_name["elasticsearch"]["error"] == "timeout(3s)"
