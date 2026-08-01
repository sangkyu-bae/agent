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
    async def test_wiki_read_included_and_policy_valid(self):
        """wiki-agentic-navigation FR-01: internal:wiki_read 카탈로그 동기화 고정."""
        from src.domain.tool_catalog.policies import ToolIdFormatPolicy

        uc, repo = _use_case()
        await uc.execute("req")
        ids = {c.args[0].tool_id for c in repo.upsert_by_tool_id.call_args_list}
        assert "internal:wiki_read" in ids
        ToolIdFormatPolicy.validate("internal:wiki_read", "internal")  # 위반 시 raise

    @pytest.mark.asyncio
    async def test_wiki_list_included_and_policy_valid(self):
        """wiki-folder-summaries FR-03: internal:wiki_list 카탈로그 동기화 고정."""
        from src.domain.tool_catalog.policies import ToolIdFormatPolicy

        uc, repo = _use_case()
        await uc.execute("req")
        ids = {c.args[0].tool_id for c in repo.upsert_by_tool_id.call_args_list}
        assert "internal:wiki_list" in ids
        ToolIdFormatPolicy.validate("internal:wiki_list", "internal")  # 위반 시 raise

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
    async def test_wiki_tools_seeded_with_builtin_default(self):
        """builtin-tools D1: INSERT 시드 — wiki 2종만 builtin_default=True 전달."""
        uc, repo = _use_case()
        await uc.execute("req")
        by_id = {
            c.args[0].tool_id: c.args[0]
            for c in repo.upsert_by_tool_id.call_args_list
        }
        assert by_id["internal:wiki_read"].is_builtin is True
        assert by_id["internal:wiki_list"].is_builtin is True
        assert by_id["internal:tavily_search"].is_builtin is False

    @pytest.mark.asyncio
    async def test_stale_deactivation_preserves_builtin(self):
        """builtin-tools D2: 레지스트리 이탈 도구 비활성화 시 is_builtin 보존."""
        stale = ToolCatalogEntry(
            id="x", tool_id="internal:removed_tool", source="internal",
            name="삭제된 도구", description="", is_active=True, is_builtin=True,
        )
        uc, repo = _use_case(existing_active=[stale])
        await uc.execute("req")
        deactivated = [
            c.args[0] for c in repo.upsert_by_tool_id.call_args_list
            if c.args[0].tool_id == "internal:removed_tool"
        ]
        assert deactivated[0].is_active is False
        assert deactivated[0].is_builtin is True

    @pytest.mark.asyncio
    async def test_resync_roundtrip_preserves_admin_builtin_flag(self):
        """builtin-tools T2②③: 관리자 토글 후 재sync 왕복에도 플래그 유지.

        fake repo가 실제 upsert의 보존 성질(UPDATE 분기는 is_builtin 미변경,
        repository 계약 테스트로 고정됨)을 흉내내어 UseCase 계층에서 왕복을 검증.
        """
        store: dict[str, ToolCatalogEntry] = {}

        async def _upsert(entry: ToolCatalogEntry, rid: str) -> ToolCatalogEntry:
            existing = store.get(entry.tool_id)
            if existing is not None:
                # 실제 repo UPDATE 분기와 동일: is_builtin은 건드리지 않는다
                existing.name = entry.name
                existing.description = entry.description
                existing.is_active = entry.is_active
                return existing
            store[entry.tool_id] = entry
            return entry

        repo = MagicMock()
        repo.upsert_by_tool_id = AsyncMock(side_effect=_upsert)
        repo.list_active = AsyncMock(
            side_effect=lambda rid: [e for e in store.values() if e.is_active]
        )
        uc = SyncInternalToolsUseCase(repository=repo, logger=MagicMock())

        # 1차 sync: 프레시 DB 시드 — wiki 2종 True
        await uc.execute("req-1")
        assert store["internal:wiki_read"].is_builtin is True
        assert store["internal:tavily_search"].is_builtin is False

        # 관리자 토글 시뮬레이션: wiki_read 해제 + tavily 등록
        store["internal:wiki_read"].is_builtin = False
        store["internal:tavily_search"].is_builtin = True

        # 재sync(재부팅) 후에도 관리자 설정 유지
        await uc.execute("req-2")
        assert store["internal:wiki_read"].is_builtin is False
        assert store["internal:tavily_search"].is_builtin is True

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
