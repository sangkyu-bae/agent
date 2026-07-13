"""SectionSummaryQueryUseCase 테스트 (Design §7.2/§7.3, D15)."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.section_summary.query_use_case import (
    SectionSummaryQueryUseCase,
)
from src.application.section_summary.schemas import (
    SectionSummaryRetryNotAllowedError,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.knowledge_base.policy import KnowledgeBasePolicy
from src.domain.section_summary.policy import SectionSummaryJobPolicy

from tests.application.section_summary.conftest import make_job

STALE_SECONDS = 600


def _user(user_id: int = 1) -> User:
    return User(
        email="t@t.com",
        password_hash="h",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=user_id,
    )


def _kb(owner_id: int = 1) -> KnowledgeBase:
    return KnowledgeBase(
        id="kb-1",
        name="여신 규정집",
        owner_id=owner_id,
        scope=CollectionScope.PERSONAL,
        collection_name="col",
    )


def _use_case(job=None, kb=None, launcher=None):
    kb_repo = AsyncMock()
    kb_repo.find_by_id.return_value = kb if kb is not None else _kb()
    dept_repo = AsyncMock()
    dept_repo.find_departments_by_user.return_value = []
    job_repo = AsyncMock()
    job_repo.find_by_document.return_value = job
    return SectionSummaryQueryUseCase(
        kb_repo=kb_repo,
        dept_repo=dept_repo,
        kb_policy=KnowledgeBasePolicy(),
        job_repo=job_repo,
        policy=SectionSummaryJobPolicy(),
        launcher=launcher or AsyncMock(),
        logger=MagicMock(),
        stale_seconds=STALE_SECONDS,
    )


class TestGetStatus:
    @pytest.mark.asyncio
    async def test_returns_status_with_progress(self):
        job = make_job(status="processing", total_sections=10, done_sections=4)
        job.updated_at = datetime.now()
        uc = _use_case(job=job)
        result = await uc.get_status("kb-1", "doc-1", _user(), "r")
        assert result.status == "processing"
        assert result.total_sections == 10
        assert result.done_sections == 4
        assert result.is_stale is False

    @pytest.mark.asyncio
    async def test_stale_processing_flagged(self):
        job = make_job(status="processing")
        job.updated_at = datetime.now() - timedelta(seconds=STALE_SECONDS + 1)
        uc = _use_case(job=job)
        result = await uc.get_status("kb-1", "doc-1", _user(), "r")
        assert result.is_stale is True

    @pytest.mark.asyncio
    async def test_no_job_raises_not_found(self):
        uc = _use_case(job=None)
        with pytest.raises(ValueError, match="not found"):
            await uc.get_status("kb-1", "doc-1", _user(), "r")

    @pytest.mark.asyncio
    async def test_kb_mismatch_raises_not_found(self):
        job = make_job(kb_id="other-kb")
        uc = _use_case(job=job)
        with pytest.raises(ValueError, match="not found"):
            await uc.get_status("kb-1", "doc-1", _user(), "r")

    @pytest.mark.asyncio
    async def test_no_read_access_raises(self):
        uc = _use_case(job=make_job(), kb=_kb(owner_id=99))
        with pytest.raises(PermissionError):
            await uc.get_status("kb-1", "doc-1", _user(), "r")


class TestRetry:
    @pytest.mark.asyncio
    async def test_failed_job_retried_via_launcher(self):
        launcher = AsyncMock()
        job = make_job(status="failed")
        job.updated_at = datetime.now()
        uc = _use_case(job=job, launcher=launcher)
        result = await uc.retry("kb-1", "doc-1", _user(), "r")
        launcher.retry.assert_awaited_once_with("job-1", "r")
        assert result.status == "processing"

    @pytest.mark.asyncio
    async def test_completed_job_retry_rejected(self):
        job = make_job(status="completed")
        job.updated_at = datetime.now()
        uc = _use_case(job=job)
        with pytest.raises(SectionSummaryRetryNotAllowedError):
            await uc.retry("kb-1", "doc-1", _user(), "r")

    @pytest.mark.asyncio
    async def test_fresh_processing_retry_rejected(self):
        job = make_job(status="processing")
        job.updated_at = datetime.now()
        uc = _use_case(job=job)
        with pytest.raises(SectionSummaryRetryNotAllowedError):
            await uc.retry("kb-1", "doc-1", _user(), "r")

    @pytest.mark.asyncio
    async def test_no_write_access_raises(self):
        uc = _use_case(job=make_job(status="failed"), kb=_kb(owner_id=99))
        with pytest.raises(PermissionError):
            await uc.retry("kb-1", "doc-1", _user(), "r")
