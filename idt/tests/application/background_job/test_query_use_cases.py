"""조회·확인 처리 use case 단위 테스트 — user_id 인가 검증 중심."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.background_job.errors import JobNotFoundError
from src.application.background_job.query_use_cases import (
    CountUnseenUseCase,
    GetJobUseCase,
    ListJobsUseCase,
    MarkAllSeenUseCase,
    MarkSeenUseCase,
)
from src.domain.background_job.entity import BackgroundJob

_NOW = datetime(2026, 8, 11, 3, 0)


def _job(job_id="j1", user_id="u1", status="success") -> BackgroundJob:
    return BackgroundJob(
        id=job_id,
        user_id=user_id,
        agent_id="a1",
        source="chat",
        query="q",
        session_id="sess-1",
        run_id="run-1",
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


class TestListJobs:
    @pytest.mark.asyncio
    async def test_maps_entities_to_responses(self):
        repo = MagicMock()
        repo.list_by_user = AsyncMock(
            return_value=[(_job("j1"), "리서치 봇"), (_job("j2"), None)]
        )
        uc = ListJobsUseCase(repo, MagicMock())
        items = await uc.execute("u1", None, 20, 0, "req-1")
        assert [i.id for i in items] == ["j1", "j2"]
        assert items[0].agent_name == "리서치 봇"
        assert items[1].agent_name is None
        repo.list_by_user.assert_awaited_once_with("u1", None, 20, 0, "req-1")


class TestGetJob:
    @pytest.mark.asyncio
    async def test_own_job_returned(self):
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=_job(user_id="u1"))
        uc = GetJobUseCase(repo, MagicMock())
        res = await uc.execute("j1", "u1", "req-1")
        assert res.id == "j1"

    @pytest.mark.asyncio
    async def test_other_users_job_hidden(self):
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=_job(user_id="someone-else"))
        uc = GetJobUseCase(repo, MagicMock())
        with pytest.raises(JobNotFoundError):
            await uc.execute("j1", "u1", "req-1")

    @pytest.mark.asyncio
    async def test_missing_job_not_found(self):
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=None)
        uc = GetJobUseCase(repo, MagicMock())
        with pytest.raises(JobNotFoundError):
            await uc.execute("nope", "u1", "req-1")


class TestSeen:
    @pytest.mark.asyncio
    async def test_count_unseen(self):
        repo = MagicMock()
        repo.count_unseen = AsyncMock(return_value=3)
        uc = CountUnseenUseCase(repo, MagicMock())
        res = await uc.execute("u1", "req-1")
        assert res.count == 3

    @pytest.mark.asyncio
    async def test_mark_seen_not_owned_raises(self):
        repo = MagicMock()
        repo.mark_seen = AsyncMock(return_value=False)
        uc = MarkSeenUseCase(repo, MagicMock())
        with pytest.raises(JobNotFoundError):
            await uc.execute("j1", "u1", "req-1")

    @pytest.mark.asyncio
    async def test_mark_all_seen_returns_count(self):
        repo = MagicMock()
        repo.mark_all_seen = AsyncMock(return_value=5)
        uc = MarkAllSeenUseCase(repo, MagicMock())
        res = await uc.execute("u1", "req-1")
        assert res.updated == 5
