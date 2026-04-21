"""ToolCatalog UseCases 단위 테스트 — Mock 의존성."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.tool_catalog.list_tool_catalog_use_case import ListToolCatalogUseCase
from src.application.tool_catalog.sync_mcp_tools_use_case import SyncMcpToolsUseCase
from src.domain.tool_catalog.entity import ToolCatalogEntry


def _make_entry(tool_id: str = "internal:tavily_search") -> ToolCatalogEntry:
    now = datetime.now(timezone.utc)
    return ToolCatalogEntry(
        id="tc-1", tool_id=tool_id, source="internal",
        name="Tavily", description="검색",
        created_at=now, updated_at=now,
    )


class TestListToolCatalogUseCase:
    @pytest.mark.asyncio
    async def test_returns_active_only(self):
        repo = MagicMock()
        repo.list_active = AsyncMock(return_value=[
            _make_entry("internal:tavily_search"),
            _make_entry("internal:excel_export"),
        ])
        uc = ListToolCatalogUseCase(repository=repo, logger=MagicMock())
        result = await uc.execute("req-1")
        assert len(result.tools) == 2
        assert result.tools[0].tool_id == "internal:tavily_search"


class TestSyncMcpToolsUseCase:
    @pytest.mark.asyncio
    async def test_sync_upserts_tools(self):
        catalog_repo = MagicMock()
        catalog_repo.upsert_by_tool_id = AsyncMock()

        server = MagicMock()
        server.id = "server-1"
        server.is_active = True

        mcp_server_repo = MagicMock()
        mcp_server_repo.find_active_all = AsyncMock(return_value=[server])

        tool1 = MagicMock()
        tool1.name = "tool_a"
        tool1.description = "A tool"
        tool2 = MagicMock()
        tool2.name = "tool_b"
        tool2.description = "B tool"

        mcp_loader = MagicMock()
        mcp_loader.list_tools = AsyncMock(return_value=[tool1, tool2])

        uc = SyncMcpToolsUseCase(
            tool_catalog_repo=catalog_repo,
            mcp_server_repo=mcp_server_repo,
            mcp_tool_loader=mcp_loader,
            logger=MagicMock(),
        )
        count = await uc.execute(None, "req-1")
        assert count == 2
        assert catalog_repo.upsert_by_tool_id.await_count == 2

    @pytest.mark.asyncio
    async def test_sync_inactive_server_deactivates_tools(self):
        catalog_repo = MagicMock()
        catalog_repo.deactivate_by_mcp_server = AsyncMock(return_value=3)

        server = MagicMock()
        server.id = "server-1"
        server.is_active = False

        mcp_server_repo = MagicMock()
        mcp_server_repo.find_active_all = AsyncMock(return_value=[server])
        mcp_loader = MagicMock()

        uc = SyncMcpToolsUseCase(
            tool_catalog_repo=catalog_repo,
            mcp_server_repo=mcp_server_repo,
            mcp_tool_loader=mcp_loader,
            logger=MagicMock(),
        )
        count = await uc.execute(None, "req-1")
        assert count == 0
        catalog_repo.deactivate_by_mcp_server.assert_awaited_once_with("server-1", "req-1")
