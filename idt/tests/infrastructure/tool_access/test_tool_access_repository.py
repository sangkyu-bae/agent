"""ToolAccessRepository — aiosqlite 실쿼리 테스트.

Design Ref: tool-access-control §3.3 — FK·CASCADE 는 DDL(V082)이 진실이고 SQLite 로는
증명하지 않는다(로컬 MySQL 적용 스크립트로 별도 확인). 여기서는 조회 합집합·
범위 한정 전체 교체·granted_by 기록을 검증한다.
"""
from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.infrastructure.persistence.models.base import Base
from src.infrastructure.tool_access.models import (
    ToolAccessDefaultModel,
    ToolAccessDepartmentModel,
    ToolAccessUserModel,
)
from src.infrastructure.tool_access.repository import ToolAccessRepository

A = "internal:excel_export"
B = "internal:python_code_executor"
C = "mcp:7f3c0000-0000-0000-0000-000000000001:search"
D = "internal:document_generator"
ALL = frozenset({A, B, C, D})


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    tables = [
        ToolAccessDefaultModel.__table__,
        ToolAccessDepartmentModel.__table__,
        ToolAccessUserModel.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
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


@pytest.fixture
def repo(session) -> ToolAccessRepository:
    return ToolAccessRepository(session=session, logger=MagicMock())


async def _seed(repo: ToolAccessRepository) -> None:
    await repo.replace_default([A], scope=ALL, granted_by=1, request_id="r")
    await repo.replace_for_department("d-loan", [B], scope=ALL, granted_by=1, request_id="r")
    await repo.replace_for_department("d-hr", [D], scope=ALL, granted_by=1, request_id="r")
    await repo.replace_for_user(12, [C], scope=ALL, granted_by=1, request_id="r")


class TestFindGrants:
    async def test_union_of_default_departments_and_user(self, repo):
        await _seed(repo)
        got = await repo.find_grants_for(12, ["d-loan"], "r")
        assert got == frozenset({A, B, C})

    async def test_multiple_departments_any_grants(self, repo):
        await _seed(repo)
        got = await repo.find_grants_for(99, ["d-loan", "d-hr"], "r")
        assert got == frozenset({A, B, D})

    async def test_no_department_no_user_grant_gets_default_only(self, repo):
        await _seed(repo)
        assert await repo.find_grants_for(99, [], "r") == frozenset({A})

    async def test_empty_tables(self, repo):
        assert await repo.find_grants_for(1, ["x"], "r") == frozenset()


class TestReplace:
    async def test_replace_default_is_full_replace(self, repo):
        await repo.replace_default([A, B], scope=ALL, granted_by=1, request_id="r")
        await repo.replace_default([C], scope=ALL, granted_by=2, request_id="r")
        assert sorted(await repo.list_default("r")) == [C]

    async def test_replace_dedupes(self, repo):
        await repo.replace_for_user(5, [A, A, B], scope=ALL, granted_by=1, request_id="r")
        assert sorted(await repo.list_for_user(5, "r")) == sorted([A, B])

    async def test_replace_keeps_rows_outside_scope(self, repo):
        # D 는 비활성 도구(scope 밖) — 편집 1회로 사라지면 재활성화 시 권한이 복원되지 않는다
        await repo.replace_for_department("d1", [A, D], scope=ALL, granted_by=1, request_id="r")
        active = frozenset({A, B, C})
        await repo.replace_for_department("d1", [B], scope=active, granted_by=1, request_id="r")
        assert sorted(await repo.list_for_department("d1", "r")) == sorted([B, D])

    async def test_replace_ignores_ids_outside_scope(self, repo):
        await repo.replace_for_user(5, [A, D], scope=frozenset({A}), granted_by=1, request_id="r")
        assert await repo.list_for_user(5, "r") == [A]

    async def test_replace_is_scoped_per_subject(self, repo):
        await repo.replace_for_department("d1", [A], scope=ALL, granted_by=1, request_id="r")
        await repo.replace_for_department("d2", [B], scope=ALL, granted_by=1, request_id="r")
        await repo.replace_for_department("d1", [], scope=ALL, granted_by=1, request_id="r")
        assert await repo.list_for_department("d1", "r") == []
        assert await repo.list_for_department("d2", "r") == [B]

    async def test_records_granted_by(self, repo, session):
        await repo.replace_for_user(5, [A], scope=ALL, granted_by=7, request_id="r")
        row = (await session.execute(select(ToolAccessUserModel))).scalar_one()
        assert row.granted_by == 7
        assert row.granted_at is not None


class TestDepartmentGrantMap:
    async def test_maps_tool_to_departments(self, repo):
        await repo.replace_for_department("d1", [A, B], scope=ALL, granted_by=1, request_id="r")
        await repo.replace_for_department("d2", [B], scope=ALL, granted_by=1, request_id="r")
        await repo.replace_for_department("d3", [C], scope=ALL, granted_by=1, request_id="r")
        got = await repo.list_department_grants(["d1", "d2"], "r")
        assert {k: sorted(v) for k, v in got.items()} == {A: ["d1"], B: ["d1", "d2"]}

    async def test_empty_departments(self, repo):
        assert await repo.list_department_grants([], "r") == {}
