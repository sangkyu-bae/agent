"""방화벽 자동 점검 어댑터 (SQLite 실제 세션) — firewall-agent design §4.4."""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.infrastructure.agent_alert.models import (
    AgentAlertReceiptModel,
    AgentAlertReceiverModel,
)
from src.infrastructure.agent_builder.models import AgentDefinitionModel
from src.infrastructure.agent_schedule.models import (
    AgentScheduleModel,
    AgentScheduleRunModel,
)

# agent_definition FK 대상(llm_model·departments)을 메타데이터에만 등록한다
from src.infrastructure.department import models as _department_models  # noqa: F401
from src.infrastructure.firewall_admin.automation_adapter import AutomationAdapter
from src.infrastructure.llm_model import models as _llm_models  # noqa: F401
from src.infrastructure.persistence.models.base import Base

NOW = datetime(2026, 11, 24, 5, 0, 0)
TABLES = [
    AgentDefinitionModel.__table__,
    AgentScheduleModel.__table__,
    AgentScheduleRunModel.__table__,
    AgentAlertReceiverModel.__table__,
    AgentAlertReceiptModel.__table__,
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


def _schedule(sid: str, *, enabled=True) -> AgentScheduleModel:
    return AgentScheduleModel(
        id=sid,
        agent_id="a1",
        user_id="7",
        name="10분 점검",
        schedule_type="cron",
        cron_expr="*/10 * * * *",
        instruction="점검",
        enabled=enabled,
        timezone="Asia/Seoul",
        next_run_at=None if not enabled else NOW,
        skip_when_busy=True,
        created_at=NOW,
        updated_at=NOW,
    )


async def _seed(factory, *, receiver=True, schedules=("s1",), enabled=True):
    async with factory() as s, s.begin():
        s.add(
            AgentDefinitionModel(
                id="a1",
                user_id="7",
                name="방화벽 보안 에이전트",
                system_prompt="p",
                llm_model_id="m",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        for sid in schedules:
            s.add(_schedule(sid, enabled=enabled))
        if schedules:
            s.add(
                AgentScheduleRunModel(
                    id="run-1",
                    schedule_id=schedules[0],
                    agent_id="a1",
                    status="skipped",
                    skip_reason="approval_pending",
                    scheduled_for=NOW - timedelta(minutes=10),
                    started_at=NOW - timedelta(minutes=10),
                    finished_at=NOW - timedelta(minutes=10),
                    request_id="r",
                )
            )
        if receiver:
            s.add(
                AgentAlertReceiverModel(
                    id="rcv-1",
                    agent_id="a1",
                    user_id="7",
                    enabled=True,
                    skip_when_busy=True,
                    token_hash="h" * 64,
                    token_hint="abcd",
                    instruction_prefix="",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            s.add(
                AgentAlertReceiptModel(
                    id="rc-1",
                    receiver_id="rcv-1",
                    agent_id="a1",
                    group_key_hash="g" * 64,
                    fingerprints_hash="f" * 64,
                    firing_count=1,
                    result="enqueued",
                    job_id="job-1",
                    received_at=NOW - timedelta(minutes=2),
                    request_id="r",
                )
            )


def _adapter(session) -> AutomationAdapter:
    return AutomationAdapter(session, MagicMock(), now_fn=lambda: NOW)


@pytest.mark.asyncio
async def test_load_snapshot(factory):
    await _seed(factory)
    async with factory() as s:
        snap = await _adapter(s).load("a1")
    assert snap.agent_name == "방화벽 보안 에이전트"
    (sch,) = snap.schedules
    assert (sch.id, sch.enabled, sch.cron_expr, sch.skip_when_busy) == (
        "s1",
        True,
        "*/10 * * * *",
        True,
    )
    assert (
        sch.last_run.status == "skipped"
        and sch.last_run.skip_reason == "approval_pending"
    )
    assert snap.alert.configured and snap.alert.enabled
    assert snap.alert.last_result == "enqueued"


@pytest.mark.asyncio
async def test_load_missing_agent_is_none(factory):
    async with factory() as s:
        assert await _adapter(s).load("nope") is None


@pytest.mark.asyncio
async def test_load_without_receiver_and_schedules(factory):
    await _seed(factory, receiver=False, schedules=())
    async with factory() as s:
        snap = await _adapter(s).load("a1")
    assert snap.schedules == () and snap.alert.configured is False


@pytest.mark.asyncio
async def test_disable_then_enable_recomputes_next_run(factory):
    await _seed(factory, schedules=("s1", "s2"))
    async with factory() as s, s.begin():
        assert await _adapter(s).set_schedules_enabled("a1", False) == 2
    async with factory() as s:
        rows = (await s.execute(select(AgentScheduleModel))).scalars().all()
        assert all(r.enabled is False for r in rows)
    async with factory() as s, s.begin():
        assert await _adapter(s).set_schedules_enabled("a1", True) == 2
    async with factory() as s:
        rows = (await s.execute(select(AgentScheduleModel))).scalars().all()
        assert all(r.enabled for r in rows)
        assert all(r.next_run_at is not None and r.next_run_at > NOW for r in rows)


@pytest.mark.asyncio
async def test_set_alert_enabled(factory):
    await _seed(factory)
    async with factory() as s, s.begin():
        assert await _adapter(s).set_alert_enabled("a1", False) is True
    async with factory() as s:
        row = (await s.execute(select(AgentAlertReceiverModel))).scalar_one()
        assert row.enabled is False


@pytest.mark.asyncio
async def test_set_alert_enabled_without_receiver(factory):
    await _seed(factory, receiver=False)
    async with factory() as s, s.begin():
        assert await _adapter(s).set_alert_enabled("a1", True) is False
