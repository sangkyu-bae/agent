"""조회·확인 처리 use case 단위 테스트 — user_id 인가 검증 중심."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.background_job.errors import JobNotFoundError
from src.application.background_job.query_use_cases import (
    CountUnseenUseCase,
    GetJobUseCase,
    ListJobHistoryUseCase,
    MarkAllSeenUseCase,
    MarkSeenUseCase,
)
from src.domain.background_job.entity import BackgroundJob, JobHistoryItem

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


class TestListJobHistory:
    def _item(self, item_id="j1", item_type="manual"):
        return JobHistoryItem(
            id=item_id,
            type=item_type,
            occurred_at=_NOW,
            title="시장 조사해줘",
            status="success",
            agent_id="a1",
            agent_name="리서치 봇",
            session_id="sess-1",
            error_message=None,
            seen_at=None,
            started_at=_NOW,
            finished_at=_NOW,
        )

    def _repo(self, items=None, total=0):
        repo = MagicMock()
        repo.list_history = AsyncMock(return_value=items or [])
        repo.count_history = AsyncMock(return_value=total)
        return repo

    @pytest.mark.asyncio
    async def test_returns_items_with_total(self):
        repo = self._repo([self._item("j1"), self._item("r1", "schedule")], 42)
        uc = ListJobHistoryUseCase(repo, MagicMock())
        res = await uc.execute("u1", "all", "all", "all", 20, 0, "req-1")
        assert [i.id for i in res.items] == ["j1", "r1"]
        assert res.total == 42

    @pytest.mark.asyncio
    async def test_deletable_flag_follows_type(self):
        """FR-11 — 스케줄 실행 행에는 휴지통을 노출하지 않는다."""
        repo = self._repo([self._item("j1"), self._item("r1", "schedule")])
        uc = ListJobHistoryUseCase(repo, MagicMock())
        res = await uc.execute("u1", "all", "all", "all", 20, 0, "req-1")
        assert res.items[0].deletable is True
        assert res.items[1].deletable is False

    @pytest.mark.asyncio
    async def test_period_converted_to_lower_bound(self):
        """FR-09 — 'all' 이 아니면 하한 시각이 repository 로 전달된다."""
        repo = self._repo()
        uc = ListJobHistoryUseCase(repo, MagicMock())
        await uc.execute("u1", "all", "all", "today", 20, 0, "req-1")
        assert repo.list_history.call_args.kwargs["since_utc"] is not None

    @pytest.mark.asyncio
    async def test_period_all_has_no_lower_bound(self):
        repo = self._repo()
        uc = ListJobHistoryUseCase(repo, MagicMock())
        await uc.execute("u1", "all", "all", "all", 20, 0, "req-1")
        assert repo.list_history.call_args.kwargs["since_utc"] is None

    @pytest.mark.asyncio
    async def test_count_uses_same_filters_as_list(self):
        """total 이 목록과 다른 조건으로 세지면 페이지 수가 틀어진다."""
        repo = self._repo()
        uc = ListJobHistoryUseCase(repo, MagicMock())
        await uc.execute("u1", "done", "manual", "week", 20, 40, "req-1")
        list_kwargs = repo.list_history.call_args.kwargs
        count_kwargs = repo.count_history.call_args.kwargs
        for key in ("status_group", "history_type", "since_utc"):
            assert list_kwargs[key] == count_kwargs[key]
        assert list_kwargs["limit"] == 20 and list_kwargs["offset"] == 40


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
