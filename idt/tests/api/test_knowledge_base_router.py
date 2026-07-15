from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.api.routes.knowledge_base_router import (
    get_kb_upload_use_case,
    get_knowledge_base_use_case,
    get_section_summary_query_use_case,
    router,
)
from src.application.section_summary.schemas import (
    SectionSummaryJobStatus,
    SectionSummaryLaunchInfo,
    SectionSummaryRetryNotAllowedError,
)
from src.application.unified_upload.schemas import (
    EsStoreResult,
    QdrantStoreResult,
    UnifiedUploadResult,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.knowledge_base.entities import KnowledgeBase
from src.interfaces.dependencies.auth import get_current_user

KB_ID = "11111111-2222-3333-4444-555555555555"


def _kb(owner_id: int = 1) -> KnowledgeBase:
    return KnowledgeBase(
        id=KB_ID,
        name="여신 규정집",
        description="설명",
        owner_id=owner_id,
        scope=CollectionScope.PERSONAL,
        department_id=None,
        collection_name="shared-col",
        status="active",
        created_at=datetime(2026, 7, 7),
        updated_at=datetime(2026, 7, 7),
    )


@pytest.fixture
def mock_use_case() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_upload_use_case() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def current_user() -> User:
    return User(
        id=1,
        email="test@example.com",
        password_hash="hashed",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
    )


@pytest.fixture
def mock_summary_query_use_case() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(
    mock_use_case: AsyncMock,
    mock_upload_use_case: AsyncMock,
    mock_summary_query_use_case: AsyncMock,
    current_user: User,
) -> TestClient:
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_knowledge_base_use_case] = lambda: mock_use_case
    app.dependency_overrides[get_kb_upload_use_case] = lambda: mock_upload_use_case
    app.dependency_overrides[get_section_summary_query_use_case] = (
        lambda: mock_summary_query_use_case
    )
    app.dependency_overrides[get_current_user] = lambda: current_user
    return TestClient(app)


class TestCreateKnowledgeBase:
    def test_returns_201(self, client: TestClient, mock_use_case: AsyncMock):
        mock_use_case.create.return_value = _kb()
        resp = client.post(
            "/api/v1/knowledge-bases",
            json={"name": "여신 규정집", "collection_name": "shared-col"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["kb_id"] == KB_ID
        assert data["name"] == "여신 규정집"
        assert data["collection_name"] == "shared-col"

    def test_duplicate_returns_409(
        self, client: TestClient, mock_use_case: AsyncMock
    ):
        mock_use_case.create.side_effect = ValueError("already exists")
        resp = client.post(
            "/api/v1/knowledge-bases",
            json={"name": "dup", "collection_name": "shared-col"},
        )
        assert resp.status_code == 409

    def test_invalid_scope_returns_422(self, client: TestClient):
        resp = client.post(
            "/api/v1/knowledge-bases",
            json={
                "name": "kb",
                "collection_name": "shared-col",
                "scope": "WORLD",
            },
        )
        assert resp.status_code == 422

    def test_collection_not_found_returns_422(
        self, client: TestClient, mock_use_case: AsyncMock
    ):
        mock_use_case.create.side_effect = ValueError("Collection 'x' not found")
        resp = client.post(
            "/api/v1/knowledge-bases",
            json={"name": "kb", "collection_name": "x"},
        )
        assert resp.status_code == 422

    def test_no_collection_access_returns_403(
        self, client: TestClient, mock_use_case: AsyncMock
    ):
        mock_use_case.create.side_effect = PermissionError("No read access")
        resp = client.post(
            "/api/v1/knowledge-bases",
            json={"name": "kb", "collection_name": "secret"},
        )
        assert resp.status_code == 403


class TestCreateWithChunking:
    def test_chunking_fields_passed_and_returned(
        self, client: TestClient, mock_use_case: AsyncMock
    ):
        kb = _kb()
        kb.use_clause_chunking = True
        kb.chunking_profile_id = "prof-1"
        kb.chunk_size = 800
        mock_use_case.create.return_value = kb
        resp = client.post(
            "/api/v1/knowledge-bases",
            json={
                "name": "규정",
                "collection_name": "shared-col",
                "use_clause_chunking": True,
                "chunking_profile_id": "prof-1",
                "chunk_size": 800,
            },
        )
        assert resp.status_code == 201
        _, kwargs = mock_use_case.create.call_args
        assert kwargs["use_clause_chunking"] is True
        assert kwargs["chunking_profile_id"] == "prof-1"
        assert kwargs["chunk_size"] == 800

    def test_override_without_switch_returns_422(
        self, client: TestClient, mock_use_case: AsyncMock
    ):
        mock_use_case.create.side_effect = ValueError(
            "chunking settings require use_clause_chunking=true"
        )
        resp = client.post(
            "/api/v1/knowledge-bases",
            json={
                "name": "규정",
                "collection_name": "shared-col",
                "chunk_size": 800,
            },
        )
        assert resp.status_code == 422


_CUSTOM_CONFIG = {
    "version": 1,
    "strategy": "boundary_pattern",
    "chunk_size": 600,
    "chunk_overlap": 80,
    "parent_chunk_size": 3000,
    "boundary_rules": [
        {"pattern": "^제\\d+장", "priority": 1, "level": "parent"},
    ],
}


class TestCreateWithCustomChunking:
    """kb-custom-chunking — create 시 커스텀 필드 왕복."""

    def test_custom_fields_passed_and_returned(
        self, client: TestClient, mock_use_case: AsyncMock
    ):
        kb = _kb()
        kb.use_custom_chunking = True
        kb.custom_chunking_config = _CUSTOM_CONFIG
        mock_use_case.create.return_value = kb
        resp = client.post(
            "/api/v1/knowledge-bases",
            json={
                "name": "커스텀",
                "collection_name": "shared-col",
                "use_custom_chunking": True,
                "custom_chunking_config": _CUSTOM_CONFIG,
            },
        )
        assert resp.status_code == 201
        _, kwargs = mock_use_case.create.call_args
        assert kwargs["use_custom_chunking"] is True
        assert kwargs["custom_chunking_config"] == _CUSTOM_CONFIG

    def test_validation_error_returns_422(
        self, client: TestClient, mock_use_case: AsyncMock
    ):
        mock_use_case.create.side_effect = ValueError(
            "use_clause_chunking and use_custom_chunking "
            "cannot both be enabled"
        )
        resp = client.post(
            "/api/v1/knowledge-bases",
            json={
                "name": "충돌",
                "collection_name": "shared-col",
                "use_clause_chunking": True,
                "use_custom_chunking": True,
                "custom_chunking_config": _CUSTOM_CONFIG,
            },
        )
        assert resp.status_code == 422


class TestUpdateChunkingSettings:
    """kb-custom-chunking D7 — PATCH /{kb_id}/chunking."""

    def _body(self, **kw) -> dict:
        body = {
            "use_clause_chunking": False,
            "chunking_profile_id": None,
            "chunk_size": None,
            "chunk_overlap": None,
            "use_custom_chunking": True,
            "custom_chunking_config": _CUSTOM_CONFIG,
        }
        body.update(kw)
        return body

    def test_returns_200_with_updated_kb(
        self, client: TestClient, mock_use_case: AsyncMock
    ):
        kb = _kb()
        kb.use_custom_chunking = True
        kb.custom_chunking_config = _CUSTOM_CONFIG
        mock_use_case.update_chunking.return_value = kb
        resp = client.patch(
            f"/api/v1/knowledge-bases/{KB_ID}/chunking",
            json=self._body(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["use_custom_chunking"] is True
        assert data["custom_chunking_config"] == _CUSTOM_CONFIG
        _, kwargs = mock_use_case.update_chunking.call_args
        assert kwargs["use_custom_chunking"] is True
        assert kwargs["custom_chunking_config"] == _CUSTOM_CONFIG

    def test_not_found_returns_404(
        self, client: TestClient, mock_use_case: AsyncMock
    ):
        mock_use_case.update_chunking.side_effect = ValueError("not found")
        resp = client.patch(
            f"/api/v1/knowledge-bases/{KB_ID}/chunking",
            json=self._body(),
        )
        assert resp.status_code == 404

    def test_no_access_returns_403(
        self, client: TestClient, mock_use_case: AsyncMock
    ):
        mock_use_case.update_chunking.side_effect = PermissionError(
            "no settings access"
        )
        resp = client.patch(
            f"/api/v1/knowledge-bases/{KB_ID}/chunking",
            json=self._body(),
        )
        assert resp.status_code == 403

    def test_invalid_settings_returns_422(
        self, client: TestClient, mock_use_case: AsyncMock
    ):
        mock_use_case.update_chunking.side_effect = ValueError(
            "invalid regex pattern '[unclosed'"
        )
        resp = client.patch(
            f"/api/v1/knowledge-bases/{KB_ID}/chunking",
            json=self._body(),
        )
        assert resp.status_code == 422
        assert "[unclosed" in resp.json()["detail"]


class TestListKnowledgeBases:
    def test_returns_200(self, client: TestClient, mock_use_case: AsyncMock):
        mock_use_case.list.return_value = [_kb()]
        resp = client.get("/api/v1/knowledge-bases")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["knowledge_bases"][0]["kb_id"] == KB_ID


class TestGetKnowledgeBase:
    def test_returns_200(self, client: TestClient, mock_use_case: AsyncMock):
        mock_use_case.get.return_value = _kb()
        resp = client.get(f"/api/v1/knowledge-bases/{KB_ID}")
        assert resp.status_code == 200
        assert resp.json()["kb_id"] == KB_ID

    def test_not_found_returns_404(
        self, client: TestClient, mock_use_case: AsyncMock
    ):
        mock_use_case.get.side_effect = ValueError("not found")
        resp = client.get(f"/api/v1/knowledge-bases/{KB_ID}")
        assert resp.status_code == 404

    def test_no_access_returns_403(
        self, client: TestClient, mock_use_case: AsyncMock
    ):
        mock_use_case.get.side_effect = PermissionError("no access")
        resp = client.get(f"/api/v1/knowledge-bases/{KB_ID}")
        assert resp.status_code == 403


class TestDeleteKnowledgeBase:
    def test_returns_200_with_cleanup_notice(
        self, client: TestClient, mock_use_case: AsyncMock
    ):
        resp = client.delete(f"/api/v1/knowledge-bases/{KB_ID}")
        assert resp.status_code == 200
        assert "vectors" in resp.json()["message"]

    def test_not_found_returns_404(
        self, client: TestClient, mock_use_case: AsyncMock
    ):
        mock_use_case.delete.side_effect = ValueError("not found")
        resp = client.delete(f"/api/v1/knowledge-bases/{KB_ID}")
        assert resp.status_code == 404

    def test_no_access_returns_403(
        self, client: TestClient, mock_use_case: AsyncMock
    ):
        mock_use_case.delete.side_effect = PermissionError("no access")
        resp = client.delete(f"/api/v1/knowledge-bases/{KB_ID}")
        assert resp.status_code == 403


class TestUploadDocument:
    def _upload_result(self) -> UnifiedUploadResult:
        return UnifiedUploadResult(
            document_id="doc-1",
            filename="test.pdf",
            total_pages=1,
            chunk_count=2,
            collection_name="shared-col",
            qdrant=QdrantStoreResult(stored_ids=["a", "b"], embedding_model="m"),
            es=EsStoreResult(indexed_count=2),
            chunking_config={
                "child_chunk_size": 500,
                "child_chunk_overlap": 50,
            },
            status="completed",
        )

    def test_returns_200_with_kb_fields(
        self, client: TestClient, mock_upload_use_case: AsyncMock
    ):
        mock_upload_use_case.execute.return_value = (
            self._upload_result(),
            _kb(),
            None,
        )
        resp = client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/documents",
            files={"file": ("test.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["kb_id"] == KB_ID
        assert data["kb_name"] == "여신 규정집"
        assert data["collection_name"] == "shared-col"
        assert data["status"] == "completed"
        assert data["chunking_strategy"] == "parent_child"
        assert data["section_summary"] is None

    def test_clause_strategy_surfaced_in_response(
        self, client: TestClient, mock_upload_use_case: AsyncMock
    ):
        result = self._upload_result()
        result.chunking_config = {"strategy": "clause_aware", "profile_id": "p1"}
        mock_upload_use_case.execute.return_value = (result, _kb(), None)
        resp = client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/documents",
            files={"file": ("test.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert resp.status_code == 200
        assert resp.json()["chunking_strategy"] == "clause_aware"

    def test_section_summary_launch_surfaced_in_response(
        self, client: TestClient, mock_upload_use_case: AsyncMock
    ):
        """요약 잡 킥오프 정보가 업로드 응답에 노출 (card-section-summary D15)."""
        mock_upload_use_case.execute.return_value = (
            self._upload_result(),
            _kb(),
            SectionSummaryLaunchInfo(job_id="job-1", status="pending"),
        )
        resp = client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/documents",
            files={"file": ("test.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert resp.status_code == 200
        assert resp.json()["section_summary"] == {
            "job_id": "job-1",
            "status": "pending",
        }

    def test_kb_not_found_returns_404(
        self, client: TestClient, mock_upload_use_case: AsyncMock
    ):
        mock_upload_use_case.execute.side_effect = ValueError("not found")
        resp = client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/documents",
            files={"file": ("test.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert resp.status_code == 404

    def test_no_write_access_returns_403(
        self, client: TestClient, mock_upload_use_case: AsyncMock
    ):
        mock_upload_use_case.execute.side_effect = PermissionError("no write")
        resp = client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/documents",
            files={"file": ("test.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert resp.status_code == 403


class TestSectionSummaryEndpoints:
    """card-section-summary §7.2/§7.3 — 상태 조회/재시도."""

    def _status(self, status: str = "processing") -> SectionSummaryJobStatus:
        return SectionSummaryJobStatus(
            job_id="job-1",
            document_id="doc-1",
            status=status,
            total_sections=10,
            done_sections=4,
            failed_sections=1,
            is_stale=False,
            error=None,
            created_at=datetime(2026, 7, 8),
            updated_at=datetime(2026, 7, 8),
        )

    def test_get_status_returns_200(
        self, client: TestClient, mock_summary_query_use_case: AsyncMock
    ):
        mock_summary_query_use_case.get_status.return_value = self._status()
        resp = client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/documents/doc-1/section-summary"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "job-1"
        assert data["status"] == "processing"
        assert data["total_sections"] == 10
        assert data["done_sections"] == 4
        assert data["failed_sections"] == 1

    def test_get_status_not_found_returns_404(
        self, client: TestClient, mock_summary_query_use_case: AsyncMock
    ):
        mock_summary_query_use_case.get_status.side_effect = ValueError(
            "Section summary job for document 'doc-1' not found"
        )
        resp = client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/documents/doc-1/section-summary"
        )
        assert resp.status_code == 404

    def test_get_status_no_access_returns_403(
        self, client: TestClient, mock_summary_query_use_case: AsyncMock
    ):
        mock_summary_query_use_case.get_status.side_effect = PermissionError(
            "no read"
        )
        resp = client.get(
            f"/api/v1/knowledge-bases/{KB_ID}/documents/doc-1/section-summary"
        )
        assert resp.status_code == 403

    def test_retry_returns_202(
        self, client: TestClient, mock_summary_query_use_case: AsyncMock
    ):
        mock_summary_query_use_case.retry.return_value = self._status(
            "processing"
        )
        resp = client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/documents/doc-1/"
            "section-summary/retry"
        )
        assert resp.status_code == 202
        assert resp.json()["status"] == "processing"

    def test_retry_not_allowed_returns_409(
        self, client: TestClient, mock_summary_query_use_case: AsyncMock
    ):
        mock_summary_query_use_case.retry.side_effect = (
            SectionSummaryRetryNotAllowedError(
                "job in status 'completed' cannot be retried"
            )
        )
        resp = client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/documents/doc-1/"
            "section-summary/retry"
        )
        assert resp.status_code == 409

    def test_retry_no_write_access_returns_403(
        self, client: TestClient, mock_summary_query_use_case: AsyncMock
    ):
        mock_summary_query_use_case.retry.side_effect = PermissionError(
            "no write"
        )
        resp = client.post(
            f"/api/v1/knowledge-bases/{KB_ID}/documents/doc-1/"
            "section-summary/retry"
        )
        assert resp.status_code == 403
