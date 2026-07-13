from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.knowledge_base.upload_use_case import (
    KnowledgeBaseUploadUseCase,
)
from src.application.unified_upload.schemas import (
    EsStoreResult,
    QdrantStoreResult,
    UnifiedUploadResult,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.knowledge_base.policy import KnowledgeBasePolicy


def _user(user_id: int = 1, role: UserRole = UserRole.USER) -> User:
    return User(
        email="test@test.com",
        password_hash="hash",
        role=role,
        status=UserStatus.APPROVED,
        id=user_id,
    )


def _kb(owner_id: int = 1) -> KnowledgeBase:
    return KnowledgeBase(
        id="11111111-2222-3333-4444-555555555555",
        name="여신 규정집",
        owner_id=owner_id,
        scope=CollectionScope.PERSONAL,
        collection_name="shared-col",
    )


def _upload_result() -> UnifiedUploadResult:
    return UnifiedUploadResult(
        document_id="doc-1",
        filename="test.pdf",
        total_pages=1,
        chunk_count=2,
        collection_name="shared-col",
        qdrant=QdrantStoreResult(stored_ids=["a"], embedding_model="m"),
        es=EsStoreResult(indexed_count=2),
        chunking_config={"child_chunk_size": 500, "child_chunk_overlap": 50},
        status="completed",
    )


@pytest.fixture
def mock_kb_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.find_by_id.return_value = _kb()
    return repo


@pytest.fixture
def mock_dept_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.find_departments_by_user.return_value = []
    return repo


@pytest.fixture
def mock_unified() -> AsyncMock:
    uc = AsyncMock()
    uc.execute.return_value = _upload_result()
    return uc


@pytest.fixture
def use_case(
    mock_kb_repo: AsyncMock,
    mock_dept_repo: AsyncMock,
    mock_unified: AsyncMock,
) -> KnowledgeBaseUploadUseCase:
    return KnowledgeBaseUploadUseCase(
        kb_repo=mock_kb_repo,
        policy=KnowledgeBasePolicy(),
        dept_repo=mock_dept_repo,
        unified_upload=mock_unified,
        logger=MagicMock(),
    )


class TestExecute:
    async def test_kb_not_found_raises(self, use_case, mock_kb_repo):
        mock_kb_repo.find_by_id.return_value = None
        with pytest.raises(ValueError, match="not found"):
            await use_case.execute(
                "ghost", _user(), b"pdf", "test.pdf", "req-1"
            )

    async def test_no_write_access_raises(self, use_case, mock_kb_repo):
        mock_kb_repo.find_by_id.return_value = _kb(owner_id=99)
        with pytest.raises(PermissionError):
            await use_case.execute(
                "kb-1", _user(user_id=1), b"pdf", "test.pdf", "req-1"
            )

    async def test_delegates_with_kb_collection_and_extra_metadata(
        self, use_case, mock_unified
    ):
        result, kb, summary_launch = await use_case.execute(
            "11111111-2222-3333-4444-555555555555",
            _user(),
            b"pdf",
            "test.pdf",
            "req-1",
        )
        assert result.status == "completed"
        assert kb.name == "여신 규정집"
        # summary_launcher 미주입 시 요약 킥오프 없음 (card-section-summary FR-10)
        assert summary_launch is None

        unified_req = mock_unified.execute.call_args[0][0]
        assert unified_req.collection_name == "shared-col"
        assert unified_req.user_id == "1"
        assert unified_req.extra_metadata == {
            "kb_id": "11111111-2222-3333-4444-555555555555",
            "kb_name": "여신 규정집",
        }

    async def test_chunk_params_passed_through(self, use_case, mock_unified):
        await use_case.execute(
            "kb-1", _user(), b"pdf", "test.pdf", "req-1",
            child_chunk_size=1000, child_chunk_overlap=100,
        )
        unified_req = mock_unified.execute.call_args[0][0]
        assert unified_req.child_chunk_size == 1000
        assert unified_req.child_chunk_overlap == 100
