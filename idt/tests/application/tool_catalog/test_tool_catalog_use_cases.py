"""ToolCatalog UseCases 단위 테스트 — Mock 의존성."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.tool_catalog.list_tool_catalog_use_case import ListToolCatalogUseCase
from src.application.tool_catalog.sync_mcp_tools_use_case import SyncMcpToolsUseCase
from src.domain.mcp_registry.interfaces import MCPServerRegistryRepositoryInterface
from src.domain.tool_catalog.entity import ToolCatalogEntry
from src.domain.tool_catalog.policies import ToolIdFormatPolicy
from src.infrastructure.mcp_registry.mcp_tool_loader import MCPToolLoader

# MCP 서버 id는 tool_id 정책상 UUID여야 한다(ToolIdFormatPolicy.MCP_PATTERN).
_SERVER_UUID = "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0"


def _make_adapter(mcp_tool_name: str):
    """MCPToolAdapter 대역 — name은 접두사가 붙고 mcp_tool_name이 원본이다."""
    tool = MagicMock()
    tool.name = f"mcp_{_SERVER_UUID.replace('-', '_')}_{mcp_tool_name}"
    tool.mcp_tool_name = mcp_tool_name
    tool.description = f"{mcp_tool_name} 설명"
    return tool


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
        mcp_server_repo.find_all_active = AsyncMock(return_value=[server])

        mcp_loader = MagicMock(spec=MCPToolLoader)
        mcp_loader.load = AsyncMock(
            return_value=[_make_adapter("tool_a"), _make_adapter("tool_b")]
        )

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
        mcp_server_repo.find_all_active = AsyncMock(return_value=[server])
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


class TestSyncMcpToolsRepositoryContract:
    """실제 리포지토리 인터페이스(spec)로 호출 계약을 검증한다.

    spec 없는 MagicMock은 존재하지 않는 메서드·잘못된 인자도 통과시키므로
    운영에서만 TypeError/AttributeError가 터졌다.
    """

    @staticmethod
    def _make_uc(mcp_server_repo):
        catalog_repo = MagicMock()
        catalog_repo.upsert_by_tool_id = AsyncMock()
        catalog_repo.deactivate_by_mcp_server = AsyncMock(return_value=0)

        loader = MagicMock(spec=MCPToolLoader)
        loader.load = AsyncMock(return_value=[_make_adapter("tool_a")])

        return SyncMcpToolsUseCase(
            tool_catalog_repo=catalog_repo,
            mcp_server_repo=mcp_server_repo,
            mcp_tool_loader=loader,
            logger=MagicMock(),
        )

    @staticmethod
    def _make_server():
        server = MagicMock()
        server.id = _SERVER_UUID
        server.is_active = True
        return server

    @pytest.mark.asyncio
    async def test_single_server_passes_request_id_to_find_by_id(self):
        repo = MagicMock(spec=MCPServerRegistryRepositoryInterface)
        repo.find_by_id = AsyncMock(return_value=self._make_server())

        count = await self._make_uc(repo).execute(_SERVER_UUID, "req-1")

        assert count == 1
        repo.find_by_id.assert_awaited_once_with(_SERVER_UUID, "req-1")

    @pytest.mark.asyncio
    async def test_all_servers_uses_find_all_active(self):
        repo = MagicMock(spec=MCPServerRegistryRepositoryInterface)
        repo.find_all_active = AsyncMock(return_value=[self._make_server()])

        count = await self._make_uc(repo).execute(None, "req-1")

        assert count == 1
        repo.find_all_active.assert_awaited_once_with("req-1")


class TestSyncMcpToolsLoaderContract:
    """MCPToolLoader의 실제 시그니처(spec)로 호출 계약을 검증한다."""

    @staticmethod
    def _make_uc(loader, catalog_repo):
        server = MagicMock()
        server.id = _SERVER_UUID
        server.is_active = True

        repo = MagicMock(spec=MCPServerRegistryRepositoryInterface)
        repo.find_all_active = AsyncMock(return_value=[server])

        return server, SyncMcpToolsUseCase(
            tool_catalog_repo=catalog_repo,
            mcp_server_repo=repo,
            mcp_tool_loader=loader,
            logger=MagicMock(),
        )

    @pytest.mark.asyncio
    async def test_loader_called_with_registration_and_request_id(self):
        catalog_repo = MagicMock()
        catalog_repo.upsert_by_tool_id = AsyncMock()
        loader = MagicMock(spec=MCPToolLoader)
        loader.load = AsyncMock(return_value=[_make_adapter("search")])

        server, uc = self._make_uc(loader, catalog_repo)
        await uc.execute(None, "req-1")

        loader.load.assert_awaited_once_with(server, "req-1")

    @pytest.mark.asyncio
    async def test_tool_id_uses_raw_mcp_tool_name_not_prefixed_name(self):
        """tool_id는 시스템 계약인 mcp:{server_id}:{mcp_tool_name}이어야 한다.

        어댑터의 .name은 'mcp_{uuid}_{tool}'로 접두사가 붙어 있어
        그대로 쓰면 tool_selection 쪽 id와 어긋난다.
        """
        catalog_repo = MagicMock()
        catalog_repo.upsert_by_tool_id = AsyncMock()
        loader = MagicMock(spec=MCPToolLoader)
        loader.load = AsyncMock(return_value=[_make_adapter("search")])

        _, uc = self._make_uc(loader, catalog_repo)
        await uc.execute(None, "req-1")

        entry = catalog_repo.upsert_by_tool_id.await_args.args[0]
        assert entry.tool_id == f"mcp:{_SERVER_UUID}:search"
        assert entry.name == "search"
        ToolIdFormatPolicy.validate(entry.tool_id, entry.source)
