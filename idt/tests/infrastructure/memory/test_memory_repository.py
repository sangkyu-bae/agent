"""MemoryRepository 통합 테스트 (SQLite + 실제 세션) — agent-memory Design §3-2.

search_history 저장소 테스트와 동일한 파일 기반 SQLite 픽스처 패턴.
"""
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

from src.domain.memory.entity import Memory, MemoryScope, MemoryStatus, MemoryType
from src.infrastructure.persistence.models.base import Base
from src.infrastructure.memory.repository import MemoryRepository


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    url = f"sqlite+aiosqlite:///{tmp.name}"
    engine = create_async_engine(url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
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


def _repo(session: AsyncSession) -> MemoryRepository:
    return MemoryRepository(session, MagicMock())


def _memory(
    user_id: str = "u1",
    mem_type: MemoryType = MemoryType.PROFILE,
    content: str = "여신 심사팀 소속",
    status: MemoryStatus = MemoryStatus.ACTIVE,
) -> Memory:
    return Memory(
        id=None,
        scope=MemoryScope.USER,
        user_id=user_id,
        tier=0,
        mem_type=mem_type,
        content=content,
        status=status,
    )


class TestSaveAndFind:
    async def test_save는_id와_타임스탬프를_채운다(self, session):
        repo = _repo(session)

        saved = await repo.save(_memory(), request_id="req-1")

        assert saved.id is not None
        assert saved.created_at is not None
        assert saved.updated_at is not None

    async def test_find_by_id_저장값_왕복(self, session):
        repo = _repo(session)
        saved = await repo.save(_memory(content="근거 조문 인용 선호"), request_id="req-1")

        found = await repo.find_by_id(saved.id, request_id="req-1")

        assert found is not None
        assert found.content == "근거 조문 인용 선호"
        assert found.mem_type == MemoryType.PROFILE
        assert found.scope == MemoryScope.USER
        assert found.status == MemoryStatus.ACTIVE

    async def test_find_by_id_미존재는_None(self, session):
        repo = _repo(session)
        assert await repo.find_by_id(999, request_id="req-1") is None


class TestFindActiveByUser:
    async def test_본인의_active만_조회(self, session):
        repo = _repo(session)
        await repo.save(_memory(user_id="u1"), request_id="req-1")
        await repo.save(
            _memory(user_id="u1", status=MemoryStatus.REJECTED), request_id="req-1"
        )
        await repo.save(_memory(user_id="u2"), request_id="req-1")

        items = await repo.find_active_by_user("u1", request_id="req-1")

        assert len(items) == 1
        assert items[0].user_id == "u1"
        assert items[0].status == MemoryStatus.ACTIVE

    async def test_count_active_by_user(self, session):
        repo = _repo(session)
        await repo.save(_memory(user_id="u1"), request_id="req-1")
        await repo.save(_memory(user_id="u1", mem_type=MemoryType.EPISODE), request_id="req-1")
        await repo.save(
            _memory(user_id="u1", status=MemoryStatus.EXPIRED), request_id="req-1"
        )

        assert await repo.count_active_by_user("u1", request_id="req-1") == 2
        assert await repo.count_active_by_user("u2", request_id="req-1") == 0


class TestFindByStatus:
    async def test_상태별_조회(self, session):
        repo = _repo(session)
        await repo.save(_memory(user_id="u1"), request_id="req-1")
        await repo.save(
            _memory(user_id="u1", status=MemoryStatus.PENDING, content="후보"),
            request_id="req-1",
        )
        await repo.save(
            _memory(user_id="u2", status=MemoryStatus.PENDING), request_id="req-1"
        )

        pending = await repo.find_by_user_and_status(
            "u1", MemoryStatus.PENDING, request_id="req-1"
        )

        assert len(pending) == 1
        assert pending[0].content == "후보"

    async def test_상태별_카운트(self, session):
        repo = _repo(session)
        await repo.save(
            _memory(user_id="u1", status=MemoryStatus.PENDING), request_id="req-1"
        )
        await repo.save(
            _memory(user_id="u1", status=MemoryStatus.PENDING, content="둘"),
            request_id="req-1",
        )
        await repo.save(_memory(user_id="u1"), request_id="req-1")

        assert (
            await repo.count_by_user_and_status(
                "u1", MemoryStatus.PENDING, request_id="req-1"
            )
            == 2
        )
        assert (
            await repo.count_by_user_and_status(
                "u2", MemoryStatus.PENDING, request_id="req-1"
            )
            == 0
        )


class TestUpdateAndDelete:
    async def test_update는_타입과_내용을_갱신(self, session):
        repo = _repo(session)
        saved = await repo.save(_memory(), request_id="req-1")
        saved.mem_type = MemoryType.DOMAIN_TERM
        saved.content = "'한도'는 동일인 여신한도"

        updated = await repo.update(saved, request_id="req-1")

        found = await repo.find_by_id(updated.id, request_id="req-1")
        assert found.mem_type == MemoryType.DOMAIN_TERM
        assert found.content == "'한도'는 동일인 여신한도"

    async def test_update는_status_전이도_영속화(self, session):
        """repo update 화이트리스트에 status 누락 시 조용히 미저장 — 회귀 가드."""
        repo = _repo(session)
        saved = await repo.save(
            _memory(status=MemoryStatus.PENDING), request_id="req-1"
        )
        saved.status = MemoryStatus.ACTIVE

        await repo.update(saved, request_id="req-1")

        found = await repo.find_by_id(saved.id, request_id="req-1")
        assert found.status == MemoryStatus.ACTIVE

    async def test_delete_성공과_미존재(self, session):
        repo = _repo(session)
        saved = await repo.save(_memory(), request_id="req-1")

        assert await repo.delete(saved.id, request_id="req-1") is True
        assert await repo.find_by_id(saved.id, request_id="req-1") is None
        assert await repo.delete(saved.id, request_id="req-1") is False
