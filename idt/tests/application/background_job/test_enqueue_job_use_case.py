"""EnqueueJobUseCase 단위 테스트 — Mock 의존성."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.background_job.enqueue_job_use_case import EnqueueJobUseCase
from src.application.background_job.errors import (
    JobConflictError,
    JobNotFoundError,
)
from src.application.background_job.schemas import EnqueueJobRequest


def _agent(visibility="private", owner="u1", department_id=None):
    agent = MagicMock()
    agent.user_id = owner
    agent.visibility = visibility
    agent.department_id = department_id
    return agent


def _make_uc(agent=None, active_job=None):
    job_repo = MagicMock()
    job_repo.enqueue = AsyncMock()
    job_repo.find_active_by_session = AsyncMock(return_value=active_job)
    agent_repo = MagicMock()
    agent_repo.find_by_id = AsyncMock(return_value=agent)
    uc = EnqueueJobUseCase(job_repo, agent_repo, MagicMock())
    return uc, job_repo, agent_repo


class TestEnqueue:
    @pytest.mark.asyncio
    async def test_accepts_and_returns_job_id(self):
        uc, job_repo, _ = _make_uc(agent=_agent(owner="u1"))
        res = await uc.execute(
            "a1", EnqueueJobRequest(query="시장 조사해줘"), "u1", [], "req-1"
        )
        assert res.status == "queued"
        assert res.job_id
        job_repo.enqueue.assert_awaited_once()
        saved = job_repo.enqueue.call_args[0][0]
        assert saved.user_id == "u1"
        assert saved.agent_id == "a1"
        assert saved.query == "시장 조사해줘"
        assert saved.status == "queued"

    @pytest.mark.asyncio
    async def test_missing_agent_raises_not_found(self):
        uc, job_repo, _ = _make_uc(agent=None)
        with pytest.raises(JobNotFoundError):
            await uc.execute(
                "nope", EnqueueJobRequest(query="q"), "u1", [], "req-1"
            )
        job_repo.enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invisible_agent_raises_not_found(self):
        # private 에이전트를 타인이 등록 시도 — 사유 비구분 404
        uc, job_repo, _ = _make_uc(agent=_agent(visibility="private", owner="owner"))
        with pytest.raises(JobNotFoundError):
            await uc.execute(
                "a1", EnqueueJobRequest(query="q"), "viewer", [], "req-1"
            )
        job_repo.enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_active_session_conflict(self):
        uc, job_repo, _ = _make_uc(
            agent=_agent(owner="u1"), active_job=MagicMock()
        )
        with pytest.raises(JobConflictError):
            await uc.execute(
                "a1",
                EnqueueJobRequest(query="q", session_id="sess-1"),
                "u1",
                [],
                "req-1",
            )
        job_repo.enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_session_skips_conflict_check(self):
        uc, job_repo, _ = _make_uc(agent=_agent(owner="u1"))
        await uc.execute("a1", EnqueueJobRequest(query="q"), "u1", [], "req-1")
        job_repo.find_active_by_session.assert_not_awaited()
        job_repo.enqueue.assert_awaited_once()
