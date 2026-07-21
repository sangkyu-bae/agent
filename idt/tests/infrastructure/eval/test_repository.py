"""MessageFeedbackRepository 통합 테스트 (SQLite + 실제 세션) — agent-eval-gate."""
from __future__ import annotations

import os
import tempfile
from typing import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.domain.eval.entity import MessageFeedback, Rating
from src.infrastructure.eval.repository import MessageFeedbackRepository
from src.infrastructure.persistence.models.base import Base


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    url = f"sqlite+aiosqlite:///{tmp.name}"
    engine = create_async_engine(url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as s:
            async with s.begin():
                yield s
    finally:
        await engine.dispose()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _repo(session):
    return MessageFeedbackRepository(session, MagicMock())


def _fb(message_id=1, user_id="u1", agent_id="a1", rating=Rating.UP, comment=None):
    return MessageFeedback(
        id=None, message_id=message_id, user_id=user_id,
        agent_id=agent_id, rating=rating, comment=comment,
    )


class TestUpsert:
    async def test_신규_삽입(self, session):
        repo = _repo(session)
        saved = await repo.upsert(_fb(comment="좋음"), "r")
        assert saved.id is not None
        assert saved.rating == Rating.UP
        assert saved.comment == "좋음"

    async def test_같은_message_user는_갱신(self, session):
        repo = _repo(session)
        await repo.upsert(_fb(rating=Rating.UP), "r")
        await repo.upsert(_fb(rating=Rating.DOWN, comment="아쉬움"), "r")

        found = await repo.find_by_message_and_user(1, "u1", "r")
        assert found.rating == Rating.DOWN
        assert found.comment == "아쉬움"
        # 유니크라 1건만
        agg = await repo.aggregate_by_agent("r")
        assert sum(u + d for _, u, d in agg) == 1

    async def test_다른_사용자는_별개(self, session):
        repo = _repo(session)
        await repo.upsert(_fb(user_id="u1"), "r")
        await repo.upsert(_fb(user_id="u2"), "r")
        assert await repo.find_by_message_and_user(1, "u1", "r") is not None
        assert await repo.find_by_message_and_user(1, "u2", "r") is not None


class TestDelete:
    async def test_취소(self, session):
        repo = _repo(session)
        await repo.upsert(_fb(), "r")
        assert await repo.delete(1, "u1", "r") is True
        assert await repo.find_by_message_and_user(1, "u1", "r") is None
        assert await repo.delete(1, "u1", "r") is False


class TestAggregate:
    async def test_에이전트별_up_down_집계(self, session):
        repo = _repo(session)
        await repo.upsert(_fb(message_id=1, user_id="u1", agent_id="a1", rating=Rating.UP), "r")
        await repo.upsert(_fb(message_id=2, user_id="u1", agent_id="a1", rating=Rating.UP), "r")
        await repo.upsert(_fb(message_id=3, user_id="u1", agent_id="a1", rating=Rating.DOWN), "r")
        await repo.upsert(_fb(message_id=4, user_id="u1", agent_id="a2", rating=Rating.UP), "r")

        agg = {row[0]: (row[1], row[2]) for row in await repo.aggregate_by_agent("r")}

        assert agg["a1"] == (2, 1)
        assert agg["a2"] == (1, 0)

    async def test_최근_부정_피드백(self, session):
        repo = _repo(session)
        await repo.upsert(_fb(message_id=1, rating=Rating.UP), "r")
        await repo.upsert(_fb(message_id=2, rating=Rating.DOWN, comment="틀림"), "r")

        neg = await repo.recent_negative(10, "r")

        assert len(neg) == 1
        assert neg[0].comment == "틀림"
