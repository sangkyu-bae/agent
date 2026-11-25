"""AgentActivityReader (SQLite 실제 세션) — firewall-agent design §10.3.

승인(approval_request)·스케줄 회차(agent_schedule_run)·백그라운드
잡(agent_background_job)
세 테이블을 읽기만 한다.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.infrastructure.agent_automation.activity_reader import AgentActivityReader
from src.infrastructure.agent_schedule.models import (
    AgentScheduleModel,
    AgentScheduleRunModel,
)
from src.infrastructure.approval.models import ApprovalRequestModel
from src.infrastructure.background_job.models import AgentBackgroundJobModel
from src.infrastructure.persistence.models.base import Base

NOW = datetime(2026, 11, 24, 5, 0, 0)
TABLES = [
    ApprovalRequestModel.__table__,
    AgentScheduleModel.__table__,
    AgentScheduleRunModel.__table__,
    AgentBackgroundJobModel.__table__,
]


@pytest.fixture
async def factory() -> AsyncGenerator[async_sessionmaker, None]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=TABLES))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    finally:
        await engine.dispose()
        os.unlink(tmp.name)


def _approval(agent_id: str, status: str, n: int = 1) -> ApprovalRequestModel:
    return ApprovalRequestModel(
        id=f"ap-{agent_id}-{status}-{n}",
        run_id=f"run-{n}",
        agent_id=agent_id,
        requested_by="7",
        worker_id="w",
        tool_id="mcp:s:block_ip",
        tool_args={},
        draft="",
        status=status,
        idempotency_key=f"k-{agent_id}-{status}-{n}",
        snapshot_version=1,
        agent_updated_at=NOW,
        resume_snapshot="{}",
        expires_at=NOW + timedelta(days=1),
        request_id="r",
        created_at=NOW,
        updated_at=NOW,
    )


def _run(
    agent_id: str, status: str, started_at: datetime, n: int = 1
) -> AgentScheduleRunModel:
    return AgentScheduleRunModel(
        id=f"sr-{agent_id}-{status}-{n}",
        schedule_id="s1",
        agent_id=agent_id,
        status=status,
        scheduled_for=started_at,
        started_at=started_at,
        request_id="r",
    )


def _job(
    agent_id: str, status: str, *, deleted: bool = False, n: int = 1
) -> AgentBackgroundJobModel:
    return AgentBackgroundJobModel(
        id=f"job-{agent_id}-{status}-{n}",
        user_id="7",
        agent_id=agent_id,
        source="api",
        query="q",
        status=status,
        queued_at=NOW,
        request_id="r",
        created_at=NOW,
        updated_at=NOW,
        deleted_at=NOW if deleted else None,
    )


async def _seed(factory: async_sessionmaker, *rows) -> None:
    async with factory() as session:
        async with session.begin():
            session.add(
                AgentScheduleModel(
                    id="s1",
                    agent_id="a1",
                    user_id="7",
                    name="n",
                    schedule_type="cron",
                    cron_expr="*/10 * * * *",
                    instruction="i",
                    enabled=True,
                    timezone="Asia/Seoul",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            session.add_all(rows)


def _reader(session: AsyncSession) -> AgentActivityReader:
    return AgentActivityReader(session, MagicMock())


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "approved", "scheduled"])
async def test_open_approval_statuses_count(factory, status):
    await _seed(factory, _approval("a1", status))
    async with factory() as session:
        assert await _reader(session).has_open_approval("a1", "req") is True


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["executed", "rejected", "expired", "failed"])
async def test_terminal_approvals_do_not_count(factory, status):
    await _seed(factory, _approval("a1", status))
    async with factory() as session:
        assert await _reader(session).has_open_approval("a1", "req") is False


@pytest.mark.asyncio
async def test_other_agents_approval_does_not_count(factory):
    await _seed(factory, _approval("a2", "pending"))
    async with factory() as session:
        assert await _reader(session).has_open_approval("a1", "req") is False


@pytest.mark.asyncio
async def test_running_schedule_run_counts_only_when_recent(factory):
    await _seed(
        factory,
        _run("a1", "running", NOW - timedelta(minutes=5), n=1),
        _run("a1", "success", NOW - timedelta(minutes=1), n=2),
    )
    async with factory() as session:
        reader = _reader(session)
        assert await reader.has_running_schedule_run(
            "a1", NOW - timedelta(minutes=30), "req"
        )
        # 30분보다 오래된 running 은 고아로 본다 (design §10.2
        # AGENT_BUSY_RUN_STALE_SECONDS)
        assert not await reader.has_running_schedule_run(
            "a1", NOW - timedelta(minutes=1), "req"
        )


@pytest.mark.asyncio
async def test_finished_schedule_runs_do_not_count(factory):
    await _seed(factory, _run("a1", "success", NOW), _run("a1", "skipped", NOW, n=2))
    async with factory() as session:
        assert not await _reader(session).has_running_schedule_run(
            "a1", NOW - timedelta(hours=1), "req"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected",
    [("queued", True), ("running", True), ("success", False), ("failed", False)],
)
async def test_active_background_job(factory, status, expected):
    await _seed(factory, _job("a1", status))
    async with factory() as session:
        assert await _reader(session).has_active_job("a1", "req") is expected


@pytest.mark.asyncio
async def test_soft_deleted_job_does_not_count(factory):
    await _seed(factory, _job("a1", "queued", deleted=True))
    async with factory() as session:
        assert await _reader(session).has_active_job("a1", "req") is False
