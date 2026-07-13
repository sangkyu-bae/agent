"""KB 업로드 → 섹션 요약 잡 킥오프 연동 테스트 (card-section-summary D14, FR-09/FR-10)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.knowledge_base.upload_use_case import (
    KnowledgeBaseUploadUseCase,
)
from src.application.section_summary.schemas import (
    SectionSummaryLaunchInfo,
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
from src.domain.section_summary.entities import SectionSummarySpec


def _user() -> User:
    return User(
        email="test@test.com",
        password_hash="hash",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=1,
    )


def _kb() -> KnowledgeBase:
    return KnowledgeBase(
        id="kb-1",
        name="여신 규정집",
        owner_id=1,
        scope=CollectionScope.PERSONAL,
        collection_name="col",
        use_clause_chunking=True,
    )


def _upload_result(status: str = "completed") -> UnifiedUploadResult:
    return UnifiedUploadResult(
        document_id="doc-1",
        filename="test.pdf",
        total_pages=1,
        chunk_count=2,
        collection_name="col",
        qdrant=QdrantStoreResult(
            stored_ids=["a"], embedding_model="text-embedding-3-small"
        ),
        es=EsStoreResult(indexed_count=2),
        chunking_config={"strategy": "clause_aware"},
        status=status,
    )


@pytest.fixture
def mock_launcher() -> AsyncMock:
    launcher = AsyncMock()
    launcher.launch.return_value = SectionSummaryLaunchInfo(
        job_id="job-1", status="pending"
    )
    return launcher


@pytest.fixture
def mock_resolver() -> AsyncMock:
    resolver = AsyncMock()
    resolver.resolve.return_value = None
    resolver.resolve_summary_spec.return_value = SectionSummarySpec(
        llm_model_id="model-1", profile_id="prof-1"
    )
    return resolver


def _use_case(resolver, launcher, upload_status="completed"):
    kb_repo = AsyncMock()
    kb_repo.find_by_id.return_value = _kb()
    dept_repo = AsyncMock()
    dept_repo.find_departments_by_user.return_value = []
    unified = AsyncMock()
    unified.execute.return_value = _upload_result(upload_status)
    return KnowledgeBaseUploadUseCase(
        kb_repo=kb_repo,
        policy=KnowledgeBasePolicy(),
        dept_repo=dept_repo,
        unified_upload=unified,
        logger=MagicMock(),
        chunking_resolver=resolver,
        summary_launcher=launcher,
    )


class TestSummaryKickoff:
    async def test_launch_called_when_spec_exists(
        self, mock_resolver, mock_launcher
    ):
        uc = _use_case(mock_resolver, mock_launcher)
        result, kb, launch = await uc.execute(
            "kb-1", _user(), b"pdf", "t.pdf", "req-1"
        )
        assert launch is not None
        assert launch.job_id == "job-1"
        launch_input = mock_launcher.launch.call_args[0][0]
        assert launch_input.document_id == "doc-1"
        assert launch_input.llm_model_id == "model-1"
        assert launch_input.embedding_model_name == "text-embedding-3-small"

    async def test_no_launch_when_summary_disabled(
        self, mock_resolver, mock_launcher
    ):
        """요약 비활성 프로파일 → 킥오프 없음, 기존 동작 불변 (FR-10 회귀 가드)."""
        mock_resolver.resolve_summary_spec.return_value = None
        uc = _use_case(mock_resolver, mock_launcher)
        result, kb, launch = await uc.execute(
            "kb-1", _user(), b"pdf", "t.pdf", "req-1"
        )
        assert launch is None
        mock_launcher.launch.assert_not_called()
        assert result.status == "completed"

    async def test_no_launch_when_upload_failed(
        self, mock_resolver, mock_launcher
    ):
        uc = _use_case(mock_resolver, mock_launcher, upload_status="failed")
        result, kb, launch = await uc.execute(
            "kb-1", _user(), b"pdf", "t.pdf", "req-1"
        )
        assert launch is None
        mock_launcher.launch.assert_not_called()

    async def test_launcher_none_result_does_not_affect_upload(
        self, mock_resolver, mock_launcher
    ):
        """launcher 실패(None 반환) 시에도 업로드 결과 정상 (FR-09)."""
        mock_launcher.launch.return_value = None
        uc = _use_case(mock_resolver, mock_launcher)
        result, kb, launch = await uc.execute(
            "kb-1", _user(), b"pdf", "t.pdf", "req-1"
        )
        assert launch is None
        assert result.status == "completed"

    async def test_no_launcher_wired_keeps_legacy_behavior(self, mock_resolver):
        uc = _use_case(mock_resolver, None)
        result, kb, launch = await uc.execute(
            "kb-1", _user(), b"pdf", "t.pdf", "req-1"
        )
        assert launch is None
