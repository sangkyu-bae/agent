"""agent_alert 저장소 (SQLite 실제 세션) — firewall-agent design §3.3 V099."""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.domain.agent_alert.entity import AlertReceipt, AlertReceiver
from src.infrastructure.agent_alert.models import (
    AgentAlertReceiptModel,
    AgentAlertReceiverModel,
)
from src.infrastructure.agent_alert.repository import (
    AlertReceiptRepository,
    AlertReceiverRepository,
)
from src.infrastructure.persistence.models.base import Base

NOW = datetime(2026, 11, 24, 7, 30, 0)


@pytest.fixture
async def factory() -> AsyncGenerator[async_sessionmaker, None]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(
                c,
                tables=[
                    AgentAlertReceiverModel.__table__,
                    AgentAlertReceiptModel.__table__,
                ],
            )
        )
    try:
        yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    finally:
        await engine.dispose()
        os.unlink(tmp.name)


def _receiver(**overrides) -> AlertReceiver:
    base = dict(
        id="rcv-1",
        agent_id="agent-1",
        user_id="7",
        enabled=True,
        skip_when_busy=True,
        token_hash="h" * 64,
        token_hint="abcd",
        instruction_prefix="정책대로",
        created_at=NOW,
        updated_at=NOW,
    )
    base.update(overrides)
    return AlertReceiver(**base)


def _receipt(n: int, *, result="enqueued", at=NOW, fp="f" * 64) -> AlertReceipt:
    return AlertReceipt(
        id=f"rc-{n}",
        receiver_id="rcv-1",
        agent_id="agent-1",
        group_key_hash="g" * 64,
        fingerprints_hash=fp,
        firing_count=1,
        result=result,
        skip_reason=None,
        job_id="job-1" if result == "enqueued" else None,
        received_at=at,
        request_id=f"req-{n}",
    )


class TestAlertReceiverRepository:
    @pytest.mark.asyncio
    async def test_save_and_find_by_agent(self, factory):
        async with factory() as session, session.begin():
            await AlertReceiverRepository(session, MagicMock()).save(_receiver(), "r")
        async with factory() as session:
            found = await AlertReceiverRepository(
                session, MagicMock()
            ).find_by_agent_id("agent-1", "r")
        assert found == _receiver()

    @pytest.mark.asyncio
    async def test_missing_agent_returns_none(self, factory):
        async with factory() as session:
            repo = AlertReceiverRepository(session, MagicMock())
            assert await repo.find_by_agent_id("nope", "r") is None

    @pytest.mark.asyncio
    async def test_update_changes_fields(self, factory):
        async with factory() as session, session.begin():
            await AlertReceiverRepository(session, MagicMock()).save(_receiver(), "r")
        changed = _receiver(enabled=False, token_hash="z" * 64, token_hint="wxyz")
        async with factory() as session, session.begin():
            await AlertReceiverRepository(session, MagicMock()).update(changed, "r")
        async with factory() as session:
            found = await AlertReceiverRepository(
                session, MagicMock()
            ).find_by_agent_id("agent-1", "r")
        assert (found.enabled, found.token_hint) == (False, "wxyz")


class TestAlertReceiptRepository:
    async def _seed(self, factory, *receipts):
        async with factory() as session, session.begin():
            await AlertReceiverRepository(session, MagicMock()).save(_receiver(), "r")
            repo = AlertReceiptRepository(session, MagicMock())
            for item in receipts:
                await repo.add(item, "r")

    @pytest.mark.asyncio
    async def test_enqueued_within_window_is_duplicate(self, factory):
        await self._seed(factory, _receipt(1, at=NOW - timedelta(minutes=3)))
        async with factory() as session:
            repo = AlertReceiptRepository(session, MagicMock())
            assert await repo.exists_enqueued_since(
                "rcv-1", "g" * 64, "f" * 64, NOW - timedelta(minutes=10), "r"
            )
            # 창 밖이면 중복 아님
            assert not await repo.exists_enqueued_since(
                "rcv-1", "g" * 64, "f" * 64, NOW - timedelta(minutes=1), "r"
            )
            # 다른 발화 집합이면 중복 아님
            assert not await repo.exists_enqueued_since(
                "rcv-1", "g" * 64, "x" * 64, NOW - timedelta(minutes=10), "r"
            )

    @pytest.mark.asyncio
    async def test_non_enqueued_results_do_not_count(self, factory):
        await self._seed(
            factory, _receipt(1, result="skipped_busy"), _receipt(2, result="disabled")
        )
        async with factory() as session:
            repo = AlertReceiptRepository(session, MagicMock())
            assert not await repo.exists_enqueued_since(
                "rcv-1", "g" * 64, "f" * 64, NOW - timedelta(minutes=10), "r"
            )

    @pytest.mark.asyncio
    async def test_list_recent_is_newest_first_and_limited(self, factory):
        await self._seed(
            factory,
            *[_receipt(i, at=NOW + timedelta(minutes=i)) for i in range(1, 6)],
        )
        async with factory() as session:
            items = await AlertReceiptRepository(session, MagicMock()).list_recent(
                "rcv-1", 3, "r"
            )
        assert [i.id for i in items] == ["rc-5", "rc-4", "rc-3"]
