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
