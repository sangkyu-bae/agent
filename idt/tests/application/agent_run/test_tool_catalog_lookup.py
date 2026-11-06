"""ToolCatalogLookup — 런타임 도구 이름 → 표시 정보 (agent-run-tool-trace Design §3.2)."""
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_run.tool_catalog_lookup import ToolCatalogLookup
from src.domain.agent_run.entities import ToolCall
from src.domain.agent_run.tool_trace_policy import ToolTraceSource
from src.domain.agent_run.value_objects import RunId
from src.domain.mcp.policy import MCPConnectionPolicy
from src.domain.tool_catalog.entity import ToolCatalogEntry

RUN = RunId("11111111-1111-1111-1111-111111111111")
T0 = datetime(2026, 11, 3, tzinfo=timezone.utc)
SERVER = "6ea2f615-515e-4f65-aabe-388970dbafbe"
RUNTIME = f"mcp_{SERVER.replace('-', '_')}_list_inquiries"


def _call(tool_name: str) -> ToolCall:
    return ToolCall(
        id="t1", run_id=RUN, step_id=None, tool_name=tool_name, llm_model_id=None,
        arguments_json=None, result_summary=None, result_json=None, token_usage=None,
        total_cost_usd=None, latency_ms=None, status="SUCCESS", error_text=None,
        created_at=T0,
    )


def _entry(
    tool_id: str, name: str, source: str = "mcp",
    requires_approval: bool = False, category: Optional[str] = None,
) -> ToolCatalogEntry:
    return ToolCatalogEntry(
        id=tool_id, tool_id=tool_id, source=source, name=name, description="",
        requires_approval=requires_approval, category=category,
    )


def _lookup(entries=None, error: Optional[Exception] = None):
    repo = MagicMock()
    repo.list_active = AsyncMock(return_value=entries or [], side_effect=error)
    logger = MagicMock()
    return ToolCatalogLookup(repo, logger), repo, logger


@pytest.mark.asyncio
class TestResolve:
    async def test_no_calls_issue_no_query(self) -> None:
        lookup, repo, _ = _lookup()
        assert await lookup.resolve([], "req") == {}
        repo.list_active.assert_not_awaited()

    async def test_mcp_entry_maps_to_runtime_name(self) -> None:
        lookup, *_ = _lookup([_entry(f"mcp:{SERVER}:list_inquiries", "list_inquiries",
                                     requires_approval=True, category="search")])
        info = (await lookup.resolve([_call(RUNTIME)], "req"))[RUNTIME]
        assert (info.display_name, info.source, info.requires_approval, info.category,
                info.tool_id) == (
            "list_inquiries", ToolTraceSource.MCP, True, "search",
            f"mcp:{SERVER}:list_inquiries",
        )

    async def test_long_mcp_name_with_hash_suffix_maps(self) -> None:
        long_tool = "extract_structured_content_from_a_very_long_named_tool"
        runtime = MCPConnectionPolicy.build_tool_name(f"mcp_{SERVER}_{long_tool}")
        lookup, *_ = _lookup([_entry(f"mcp:{SERVER}:{long_tool}", long_tool)])
        assert runtime in await lookup.resolve([_call(runtime)], "req")

    async def test_internal_entry_maps_to_bare_name(self) -> None:
        # 실DB 확인(2026-11-03): internal:<런타임 이름> 1:1.
        lookup, *_ = _lookup([_entry("internal:tavily_search", "Tavily 웹 검색", "internal")])
        info = (await lookup.resolve([_call("tavily_search")], "req"))["tavily_search"]
        assert (info.display_name, info.source) == ("Tavily 웹 검색", ToolTraceSource.INTERNAL)

    async def test_server_level_mcp_entry_is_ignored(self) -> None:
        lookup, *_ = _lookup([_entry(f"mcp:{SERVER}", "server")])
        assert await lookup.resolve([_call(RUNTIME)], "req") == {}

    async def test_unparseable_tool_id_is_ignored(self) -> None:
        lookup, *_ = _lookup([_entry("custom-thing", "x", "custom")])
        assert await lookup.resolve([_call("x")], "req") == {}

    async def test_catalog_failure_returns_empty_and_warns(self) -> None:
        error = RuntimeError("db down")
        lookup, _, logger = _lookup(error=error)
        assert await lookup.resolve([_call(RUNTIME)], "req") == {}
        assert logger.warning.call_args.kwargs["exception"] is error
