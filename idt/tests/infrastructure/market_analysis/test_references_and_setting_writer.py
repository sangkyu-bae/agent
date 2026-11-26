"""참조 확인 어댑터 · 설정 쓰기 (module-8 §5.2)."""

from __future__ import annotations

import dataclasses
import os
import tempfile
from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.domain.market_analysis.setting import MarketAnalysisSetting
from src.infrastructure.market_analysis.adapters.references import (
    PlatformReferenceChecker,
)
from src.infrastructure.market_analysis.models import MaSettingModel
from src.infrastructure.market_analysis.repositories import (
    SessionSettingWriter,
    SettingRepository,
)
from src.infrastructure.persistence.models.base import Base


def _checker(server=None, ctx=None, agent=None, boom=False):
    async def find(server_id, request_id):
        if boom:
            raise RuntimeError("db down")
        return server

    async def assemble(user_id, request_id):
        if boom:
            raise RuntimeError("db down")
        return ctx

    @asynccontextmanager
    async def sf():
        yield object()

    class Repo:
        def __init__(self, session, logger):
            pass

        async def find_by_id(self, agent_id, request_id):
            if boom:
                raise RuntimeError("db down")
            return agent

    checker = PlatformReferenceChecker(
        session_factory=sf,
        server_finder=find,
        auth_ctx_assembler=assemble,
        logger=MagicMock(),
    )
    return checker, Repo


async def test_reference_checks():
    checker, repo_cls = _checker(
        server=SimpleNamespace(is_active=True),
        ctx=object(),
        agent=SimpleNamespace(status="active"),
    )
    with patch(
        "src.infrastructure.market_analysis.adapters.references."
        "AgentDefinitionRepository",
        repo_cls,
    ):
        assert await checker.mcp_server_active("kis-1", "r") is True
        assert await checker.user_active("7", "r") is True
        assert await checker.agent_usable("a1", "r") is True

    checker, repo_cls = _checker(
        server=SimpleNamespace(is_active=False),
        ctx=None,
        agent=SimpleNamespace(status="deleted"),
    )
    with patch(
        "src.infrastructure.market_analysis.adapters.references."
        "AgentDefinitionRepository",
        repo_cls,
    ):
        assert await checker.mcp_server_active("kis-1", "r") is False
        assert await checker.user_active("7", "r") is False
        assert await checker.agent_usable("a1", "r") is False


async def test_lookup_failures_are_false():
    checker, repo_cls = _checker(boom=True)
    with patch(
        "src.infrastructure.market_analysis.adapters.references."
        "AgentDefinitionRepository",
        repo_cls,
    ):
        assert await checker.mcp_server_active("x", "r") is False
        assert await checker.user_active("x", "r") is False
        assert await checker.agent_usable("x", "r") is False


@pytest.fixture
async def factory():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: Base.metadata.create_all(c, tables=[MaSettingModel.__table__])
        )
    try:
        yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    finally:
        await engine.dispose()
        os.unlink(tmp.name)


async def test_setting_writer_round_trip_and_overwrite(factory):
    writer = SessionSettingWriter(factory, MagicMock())
    s = dataclasses.replace(
        MarketAnalysisSetting.defaults(),
        enabled=True,
        kis_server_id="kis-1",
        run_as_user_id="7",
        round_times=("09:30", "15:40"),
        min_rr=Decimal("2.5"),
        condition_seqs=("0", "3"),
    )
    await writer.save(s, updated_by="3", request_id="r")
    await writer.save(
        dataclasses.replace(s, max_per_round=10), updated_by="4", request_id="r"
    )
    async with factory() as session:
        loaded = await SettingRepository(session, MagicMock()).get("r")
        row = await session.get(MaSettingModel, 1)
    assert loaded == dataclasses.replace(s, max_per_round=10)
    assert row.updated_by == "4"
