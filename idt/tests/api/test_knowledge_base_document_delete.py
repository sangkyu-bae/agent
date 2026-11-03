"""KB 문서 삭제 API — kb-document-management Design §8.2 L1 #1~12.

실제 가드·정책·UseCase를 조립하고 저장소만 대체해 판정 순서를 실요청으로 검증한다.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.knowledge_base_router import (
    get_delete_kb_document_use_case,
    get_list_kb_documents_use_case,
    router,
)
from src.application.doc_browse.delete_document_use_case import (
    DeleteDocumentUseCase,
)
from src.application.knowledge_base.content_browse_guard import KbDocumentGuard
from src.application.knowledge_base.delete_document_use_case import (
    DeleteKbDocumentUseCase,
)
from src.application.knowledge_base.list_documents_use_case import (
    ListKbDocumentsUseCase,
)
from src.application.knowledge_base.use_case import KnowledgeBaseUseCase
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.doc_browse.policies import DocumentDeletePolicy
from src.domain.doc_browse.schemas import DocumentMetadata, KbDocumentSummary
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.knowledge_base.policy import KnowledgeBasePolicy
from src.domain.mysql.schemas import MySQLPageResult
from src.domain.section_summary.entities import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_PROCESSING,
    SectionSummaryJob,
)
from src.domain.section_summary.policy import SectionSummaryJobPolicy
from src.interfaces.dependencies.auth import get_current_user

KB_ID = "kb-1"
DOC_ID = "doc-1"
URL = f"/api/v1/knowledge-bases/{KB_ID}/documents/{DOC_ID}"
STALE_SECONDS = 600
OWNER = 1
UPLOADER = 2
MEMBER = 3
OUTSIDER = 4


def _user(user_id: int, role: UserRole = UserRole.USER) -> User:
    return User(
        id=user_id,
        email="t@t.com",
        password_hash="h",
        role=role,
        status=UserStatus.APPROVED,
    )


def _kb(scope: CollectionScope = CollectionScope.DEPARTMENT) -> KnowledgeBase:
    return KnowledgeBase(
        id=KB_ID,
        name="여신 규정집",
        owner_id=OWNER,
        scope=scope,
        department_id=(
            "dept-1" if scope == CollectionScope.DEPARTMENT else None
        ),
        collection_name="shared-col",
    )


def _meta(kb_id: str | None = KB_ID) -> DocumentMetadata:
    return DocumentMetadata(
        document_id=DOC_ID,
        collection_name="shared-col",
        filename="규정.pdf",
        category="kb",
        user_id=str(UPLOADER),
        chunk_count=4,
        chunk_strategy="parent_child",
        kb_id=kb_id,
    )


def _job(status: str, updated_ago_seconds: int = 0) -> SectionSummaryJob:
    return SectionSummaryJob(
        id="job-1",
        document_id=DOC_ID,
        kb_id=KB_ID,
        collection_name="shared-col",
        chunking_profile_id="p-1",
        llm_model_id="m-1",
        embedding_provider="openai",
        embedding_model="e-1",
        status=status,
        updated_at=datetime.now() - timedelta(seconds=updated_ago_seconds),
    )


class Harness:
    """저장소만 대체한 조립체. 상태를 바꿔 가며 같은 라우트를 호출한다."""

    def __init__(self) -> None:
        self.current = _user(OWNER)
        self.kb_repo = AsyncMock()
        self.kb_repo.find_by_id.return_value = _kb()
        self.dept_repo = AsyncMock()
        self.dept_repo.find_departments_by_user.return_value = [
            SimpleNamespace(department_id="dept-1")
        ]
        self.metadata_repo = AsyncMock()
        self.metadata_repo.find_by_document_id.return_value = _meta()
        self.job_repo = AsyncMock()
        self.job_repo.find_by_document.return_value = None
        self.qdrant = AsyncMock()
        self.qdrant.count.return_value = MagicMock(count=4)
        self.es_repo = AsyncMock()
        self.es_repo.delete_by_query.return_value = 4
        logger = MagicMock()
        self.kb_use_case = KnowledgeBaseUseCase(
            kb_repo=self.kb_repo,
            policy=KnowledgeBasePolicy(),
            assigner=AsyncMock(),
            dept_repo=self.dept_repo,
            logger=logger,
        )
        deleter = DeleteDocumentUseCase(
            document_metadata_repo=self.metadata_repo,
            qdrant_client=self.qdrant,
            es_repo=self.es_repo,
            es_index="documents",
            permission_service=AsyncMock(),
            activity_log_service=AsyncMock(),
            policy=DocumentDeletePolicy(),
            logger=logger,
        )
        self.use_case = DeleteKbDocumentUseCase(
            guard=KbDocumentGuard(
                kb_use_case=self.kb_use_case,
                document_metadata_repo=self.metadata_repo,
                logger=logger,
            ),
            deleter=deleter,
            job_repo=self.job_repo,
            policy=KnowledgeBasePolicy(),
            job_policy=SectionSummaryJobPolicy(),
            logger=logger,
            stale_seconds=STALE_SECONDS,
        )
        self.list_use_case = ListKbDocumentsUseCase(
            kb_use_case=self.kb_use_case,
            document_metadata_repo=self.metadata_repo,
            logger=logger,
        )

    def assert_nothing_deleted(self) -> None:
        self.qdrant.delete.assert_not_awaited()
        self.es_repo.delete_by_query.assert_not_awaited()
        self.metadata_repo.delete_by_document_id.assert_not_awaited()
        self.job_repo.delete_by_document.assert_not_awaited()


@pytest.fixture
def harness() -> Harness:
    return Harness()


@pytest.fixture
def client(harness: Harness) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_delete_kb_document_use_case] = (
        lambda: harness.use_case
    )
    app.dependency_overrides[get_list_kb_documents_use_case] = (
        lambda: harness.list_use_case
    )
    app.dependency_overrides[get_current_user] = lambda: harness.current
    return TestClient(app)


class TestDeleteAllowed:
    def test_owner(self, client, harness):
        resp = client.delete(URL)

        assert resp.status_code == 200
        assert resp.json() == {
            "kb_id": KB_ID,
            "document_id": DOC_ID,
            "filename": "규정.pdf",
            "deleted_qdrant_chunks": 4,
            "deleted_es_chunks": 4,
            "status": "deleted",
        }
        harness.qdrant.delete.assert_awaited_once()
        harness.es_repo.delete_by_query.assert_awaited_once()
        harness.metadata_repo.delete_by_document_id.assert_awaited_once()
        harness.job_repo.delete_by_document.assert_awaited_once()

    def test_admin(self, client, harness):
        harness.current = _user(OUTSIDER, UserRole.ADMIN)
        assert client.delete(URL).status_code == 200

    def test_uploader_in_department_kb(self, client, harness):
        harness.current = _user(UPLOADER)
        assert client.delete(URL).status_code == 200


class TestDeleteDenied:
    def test_department_member_for_others_document(self, client, harness):
        harness.current = _user(MEMBER)

        resp = client.delete(URL)

        assert resp.status_code == 403
        harness.assert_nothing_deleted()

    def test_public_reader(self, client, harness):
        harness.current = _user(OUTSIDER)
        harness.kb_repo.find_by_id.return_value = _kb(CollectionScope.PUBLIC)

        resp = client.delete(URL)

        assert resp.status_code == 403
        harness.assert_nothing_deleted()

    def test_no_read_access(self, client, harness):
        harness.current = _user(OUTSIDER)
        harness.dept_repo.find_departments_by_user.return_value = []

        assert client.delete(URL).status_code == 403
        harness.metadata_repo.find_by_document_id.assert_not_awaited()
        harness.assert_nothing_deleted()


class TestDeleteNotFound:
    def test_document_of_other_kb(self, client, harness):
        harness.metadata_repo.find_by_document_id.return_value = _meta("kb-2")

        assert client.delete(URL).status_code == 404
        harness.assert_nothing_deleted()

    def test_legacy_document_without_kb(self, client, harness):
        harness.metadata_repo.find_by_document_id.return_value = _meta(None)

        assert client.delete(URL).status_code == 404

    def test_missing_document(self, client, harness):
        harness.metadata_repo.find_by_document_id.return_value = None

        assert client.delete(URL).status_code == 404

    def test_missing_kb(self, client, harness):
        harness.kb_repo.find_by_id.return_value = None

        assert client.delete(URL).status_code == 404


class TestSummaryJob:
    def test_active_job_returns_409_with_message(self, client, harness):
        harness.job_repo.find_by_document.return_value = _job(
            JOB_STATUS_PROCESSING
        )

        resp = client.delete(URL)

        assert resp.status_code == 409
        assert "요약" in resp.json()["detail"]
        harness.assert_nothing_deleted()

    def test_permission_checked_before_job(self, client, harness):
        harness.current = _user(MEMBER)
        harness.job_repo.find_by_document.return_value = _job(
            JOB_STATUS_PROCESSING
        )

        assert client.delete(URL).status_code == 403

    @pytest.mark.parametrize(
        "job",
        [
            None,
            _job(JOB_STATUS_COMPLETED),
            _job(JOB_STATUS_FAILED),
            _job(JOB_STATUS_PROCESSING, STALE_SECONDS + 60),
        ],
    )
    def test_inactive_or_stale_job_allows(self, client, harness, job):
        harness.job_repo.find_by_document.return_value = job

        assert client.delete(URL).status_code == 200


class TestStoreFailure:
    def test_es_failure_returns_503_and_keeps_metadata(self, client, harness):
        harness.es_repo.delete_by_query.side_effect = RuntimeError("es down")

        resp = client.delete(URL)

        assert resp.status_code == 503
        assert "다시 시도" in resp.json()["detail"]
        harness.metadata_repo.delete_by_document_id.assert_not_awaited()
        harness.job_repo.delete_by_document.assert_not_awaited()

    def test_retry_succeeds_after_recovery(self, client, harness):
        harness.es_repo.delete_by_query.side_effect = RuntimeError("es down")
        assert client.delete(URL).status_code == 503

        harness.es_repo.delete_by_query.side_effect = None
        harness.qdrant.count.return_value = MagicMock(count=0)

        resp = client.delete(URL)

        assert resp.status_code == 200
        assert resp.json()["deleted_qdrant_chunks"] == 0
        harness.metadata_repo.delete_by_document_id.assert_awaited_once()


class TestDocumentList:
    def test_can_delete_per_document(self, client, harness):
        harness.current = _user(UPLOADER)
        harness.metadata_repo.find_by_kb_id.return_value = MySQLPageResult(
            items=[
                KbDocumentSummary(
                    document_id="mine",
                    filename="a.pdf",
                    chunk_count=1,
                    chunk_strategy="parent_child",
                    created_at=None,
                    user_id=str(UPLOADER),
                ),
                KbDocumentSummary(
                    document_id="others",
                    filename="b.pdf",
                    chunk_count=1,
                    chunk_strategy="parent_child",
                    created_at=None,
                    user_id=str(MEMBER),
                ),
            ],
            total=2,
            limit=20,
            offset=0,
        )

        resp = client.get(f"/api/v1/knowledge-bases/{KB_ID}/documents")

        assert resp.status_code == 200
        flags = {
            d["document_id"]: d["can_delete"]
            for d in resp.json()["documents"]
        }
        assert flags == {"mine": True, "others": False}


def test_requires_authentication(harness):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_delete_kb_document_use_case] = (
        lambda: harness.use_case
    )

    resp = TestClient(app).delete(URL)

    assert resp.status_code == 401
    harness.assert_nothing_deleted()
