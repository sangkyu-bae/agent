"""삭제·정리 use case 단위 테스트 (jobs-page-revamp FR-03~05)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.background_job.delete_use_cases import (
    CleanupJobsUseCase,
    DeleteJobUseCase,
)
from src.application.background_job.errors import (
    JobDeleteConflictError,
    JobNotFoundError,
)
from src.domain.background_job.entity import BackgroundJob

_NOW = datetime(2026, 9, 3, 10, 0)


def _job(user_id="u1", status="success") -> BackgroundJob:
    return BackgroundJob(
        id="j1",
        user_id=user_id,
        agent_id="a1",
        source="chat",
        query="q",
        session_id=None,
        run_id=None,
        status=status,
        error_message=None,
        seen_at=None,
        queued_at=_NOW,
        started_at=_NOW,
        finished_at=_NOW,
        request_id="req-0",
        created_at=_NOW,
        updated_at=_NOW,
    )


def _repo(job=None, deleted=True):
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=job)
    repo.soft_delete = AsyncMock(return_value=deleted)
    repo.soft_delete_completed = AsyncMock(return_value=0)
    return repo


class TestDeleteJob:
    @pytest.mark.asyncio
    async def test_completed_job_soft_deleted(self):
        repo = _repo(_job(status="failed"))
        await DeleteJobUseCase(repo, MagicMock()).execute("j1", "u1", "req-1")
        repo.soft_delete.assert_awaited_once()
        assert repo.soft_delete.call_args[0][:2] == ("j1", "u1")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", ["queued", "running"])
    async def test_active_job_rejected_as_conflict(self, status):
        """FR-04 — 워커가 소유한 상태를 사용자가 지우면 고아 상태가 남는다."""
        repo = _repo(_job(status=status))
        with pytest.raises(JobDeleteConflictError):
            await DeleteJobUseCase(repo, MagicMock()).execute(
                "j1", "u1", "req-1"
            )
        repo.soft_delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_other_users_job_not_found(self):
        repo = _repo(_job(user_id="someone-else"))
        with pytest.raises(JobNotFoundError):
            await DeleteJobUseCase(repo, MagicMock()).execute(
                "j1", "u1", "req-1"
            )
        repo.soft_delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_job_not_found(self):
        repo = _repo(None)
        with pytest.raises(JobNotFoundError):
            await DeleteJobUseCase(repo, MagicMock()).execute(
                "nope", "u1", "req-1"
            )

    @pytest.mark.asyncio
    async def test_concurrent_delete_reports_not_found(self):
        """find 이후 다른 요청이 먼저 지운 경우 — 사라진 자원이므로 404."""
        repo = _repo(_job(), deleted=False)
        with pytest.raises(JobNotFoundError):
            await DeleteJobUseCase(repo, MagicMock()).execute(
                "j1", "u1", "req-1"
            )


class TestCleanupJobs:
    @pytest.mark.asyncio
    async def test_returns_deleted_count(self):
        repo = _repo()
        repo.soft_delete_completed = AsyncMock(return_value=3)
        res = await CleanupJobsUseCase(repo, MagicMock()).execute("u1", "req-1")
        assert res.deleted == 3
        assert repo.soft_delete_completed.call_args[0][0] == "u1"

    @pytest.mark.asyncio
    async def test_no_targets_is_not_an_error(self):
        repo = _repo()
        res = await CleanupJobsUseCase(repo, MagicMock()).execute("u1", "req-1")
        assert res.deleted == 0
