"""SyncInternalToolsUseCase 테스트 — TOOL_REGISTRY → tool_catalog 동기화.

코드(TOOL_REGISTRY)를 내부 도구 단일 진실원으로 삼아 부팅 시 tool_catalog에 반영.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.tool_catalog.sync_internal_tools_use_case import (
    SyncInternalToolsUseCase,
)
from src.domain.agent_builder.tool_registry import get_all_tools
from src.domain.tool_catalog.entity import ToolCatalogEntry


def _use_case(existing_active: list[ToolCatalogEntry] | None = None):
    repo = MagicMock()
    repo.upsert_by_tool_id = AsyncMock(side_effect=lambda e, rid: e)
    repo.list_active = AsyncMock(return_value=existing_active or [])
    return SyncInternalToolsUseCase(repository=repo, logger=MagicMock()), repo


class TestSyncInternalTools:
    @pytest.mark.asyncio
    async def test_upserts_every_registry_tool_with_internal_prefix(self):
        uc, repo = _use_case()
        await uc.execute("req")

        upserted = [c.args[0] for c in repo.upsert_by_tool_id.call_args_list]
        by_tool_id = {e.tool_id: e for e in upserted}
        # TOOL_REGISTRY 전 도구가 internal:{id}로 반영
        for meta in get_all_tools():
            key = f"internal:{meta.tool_id}"
            assert key in by_tool_id, f"{key} 미동기화"
            assert by_tool_id[key].source == "internal"
            assert by_tool_id[key].is_active is True
            assert by_tool_id[key].name == meta.name

    @pytest.mark.asyncio
    async def test_document_extractor_included(self):
        uc, repo = _use_case()
        await uc.execute("req")
        ids = {c.args[0].tool_id for c in repo.upsert_by_tool_id.call_args_list}
        assert "internal:document_extractor" in ids
        assert "internal:data_analysis" in ids

    @pytest.mark.asyncio
    async def test_requires_env_carried_over(self):
        uc, repo = _use_case()
        await uc.execute("req")
        by_id = {c.args[0].tool_id: c.args[0] for c in repo.upsert_by_tool_id.call_args_list}
        # tavily_search는 TAVILY_API_KEY 필요
        assert "TAVILY_API_KEY" in by_id["internal:tavily_search"].requires_env

    @pytest.mark.asyncio
    async def test_stale_internal_tool_deactivated(self):
        stale = ToolCatalogEntry(
            id="x", tool_id="internal:removed_tool", source="internal",
            name="삭제된 도구", description="", is_active=True,
        )
        uc, repo = _use_case(existing_active=[stale])
        await uc.execute("req")
        deactivated = [
            c.args[0] for c in repo.upsert_by_tool_id.call_args_list
            if c.args[0].tool_id == "internal:removed_tool"
        ]
        assert len(deactivated) == 1
        assert deactivated[0].is_active is False

    @pytest.mark.asyncio
    async def test_mcp_entries_not_touched(self):
        mcp = ToolCatalogEntry(
            id="m", tool_id="mcp:srv:tool", source="mcp",
            name="MCP 도구", description="", is_active=True,
        )
        uc, repo = _use_case(existing_active=[mcp])
        await uc.execute("req")
        touched = {c.args[0].tool_id for c in repo.upsert_by_tool_id.call_args_list}
        assert "mcp:srv:tool" not in touched
