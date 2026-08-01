"""ToolCatalogRepository 단위 테스트 — AsyncMock 사용."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.tool_catalog.entity import ToolCatalogEntry
from src.infrastructure.tool_catalog.tool_catalog_repository import ToolCatalogRepository


def _make_entry(tool_id: str = "internal:tavily_search") -> ToolCatalogEntry:
    now = datetime.now(timezone.utc)
    return ToolCatalogEntry(
        id="tc-1", tool_id=tool_id, source="internal",
        name="Tavily 검색", description="웹 검색",
        created_at=now, updated_at=now,
    )


def _make_repo() -> tuple[ToolCatalogRepository, MagicMock]:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    logger = MagicMock()
    return ToolCatalogRepository(session=session, logger=logger), session


class TestToolCatalogRepositorySave:
    @pytest.mark.asyncio
    async def test_save_adds_and_flushes(self):
        repo, session = _make_repo()
        entry = _make_entry()
        result = await repo.save(entry, "req-1")
        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        assert result.tool_id == entry.tool_id


class TestToolCatalogRepositoryUpsert:
    @pytest.mark.asyncio
    async def test_upsert_inserts_when_not_exists(self):
        repo, session = _make_repo()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        entry = _make_entry()
        await repo.upsert_by_tool_id(entry, "req-1")
        session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_updates_when_exists(self):
        repo, session = _make_repo()
        now = datetime.now(timezone.utc)
        existing_model = MagicMock()
        existing_model.id = "tc-1"
        existing_model.tool_id = "internal:tavily_search"
        existing_model.source = "internal"
        existing_model.name = "old"
        existing_model.description = "old"
        existing_model.mcp_server_id = None
        existing_model.requires_env = None
        existing_model.is_active = True
        existing_model.created_at = now
        existing_model.updated_at = now

        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                r = MagicMock()
                r.scalar_one_or_none.return_value = existing_model
                return r
            r = MagicMock()
            r.rowcount = 1
            return r

        session.execute = mock_execute

        entry = _make_entry()
        await repo.upsert_by_tool_id(entry, "req-1")
        session.add.assert_not_called()


class TestToolCatalogRepositoryBuiltin:
    @pytest.mark.asyncio
    async def test_save_carries_is_builtin(self):
        """builtin-tools D1: INSERT 경로는 entity의 is_builtin을 그대로 영속."""
        repo, session = _make_repo()
        entry = _make_entry()
        entry.is_builtin = True
        await repo.save(entry, "req-1")
        model = session.add.call_args.args[0]
        assert model.is_builtin is True

    @pytest.mark.asyncio
    async def test_upsert_update_branch_never_touches_is_builtin(self):
        """builtin-tools D2 보존 계약: UPDATE SET 절에 is_builtin이 없어야 한다.

        관리자 토글값이 부팅 sync의 upsert로 덮어써지지 않는 근거가 이 성질이므로
        테스트로 계약화한다.
        """
        repo, session = _make_repo()
        now = datetime.now(timezone.utc)
        existing_model = MagicMock()
        existing_model.id = "tc-1"
        existing_model.tool_id = "internal:wiki_read"
        existing_model.source = "internal"
        existing_model.name = "old"
        existing_model.description = "old"
        existing_model.mcp_server_id = None
        existing_model.requires_env = None
        existing_model.is_active = True
        existing_model.is_builtin = True
        existing_model.created_at = now
        existing_model.updated_at = now

        captured_stmts = []
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            captured_stmts.append(stmt)
            if call_count == 1:
                r = MagicMock()
                r.scalar_one_or_none.return_value = existing_model
                return r
            r = MagicMock()
            r.rowcount = 1
            return r

        session.execute = mock_execute

        entry = _make_entry("internal:wiki_read")
        entry.is_builtin = False  # sync가 넘기는 기본값이 와도
        await repo.upsert_by_tool_id(entry, "req-1")

        update_stmt = captured_stmts[1]
        set_columns = set(update_stmt.compile().params.keys())
        assert "is_builtin" not in set_columns

    @pytest.mark.asyncio
    async def test_set_builtin_updates_flag(self):
        """builtin-tools D3: set_builtin — is_builtin/updated_at만 UPDATE."""
        repo, session = _make_repo()
        captured_stmts = []
        call_count = 0
        now = datetime.now(timezone.utc)
        existing_model = MagicMock()
        existing_model.id = "tc-1"
        existing_model.tool_id = "internal:wiki_read"
        existing_model.source = "internal"
        existing_model.name = "위키 열람"
        existing_model.description = "d"
        existing_model.mcp_server_id = None
        existing_model.requires_env = None
        existing_model.is_active = True
        existing_model.is_builtin = True
        existing_model.created_at = now
        existing_model.updated_at = now

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            captured_stmts.append(stmt)
            r = MagicMock()
            if call_count == 1:
                r.rowcount = 1
                return r
            r.scalar_one_or_none.return_value = existing_model
            return r

        session.execute = mock_execute

        result = await repo.set_builtin("internal:wiki_read", True, "req-1")
        set_columns = set(captured_stmts[0].compile().params.keys())
        assert "is_builtin" in set_columns
        assert result is not None and result.is_builtin is True

    @pytest.mark.asyncio
    async def test_list_builtin_filters_active_and_builtin(self):
        """builtin-tools D5: 주입 대상은 is_builtin AND is_active."""
        repo, session = _make_repo()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        await repo.list_builtin("req-1")
        stmt = session.execute.call_args.args[0]
        where_sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "is_builtin" in where_sql
        assert "is_active" in where_sql


class TestToolCatalogRepositoryDeactivate:
    @pytest.mark.asyncio
    async def test_deactivate_by_mcp_server(self):
        repo, session = _make_repo()
        mock_result = MagicMock()
        mock_result.rowcount = 3
        session.execute = AsyncMock(return_value=mock_result)

        count = await repo.deactivate_by_mcp_server("server-1", "req-1")
        assert count == 3
        session.flush.assert_awaited_once()
