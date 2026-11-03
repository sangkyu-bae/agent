"""RunSourcesService — 증거 수집과 실패 흡수 (agent-run-source-citations §2.1, §6.1)."""
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_run.run_sources import RunSourcesService
from src.domain.agent_run.entities import RetrievalSource, ToolCall
from src.domain.agent_run.source_policy import SourceKind
from src.domain.agent_run.value_objects import RunId
from src.domain.mcp.policy import MCPConnectionPolicy
from src.domain.tool_catalog.entity import ToolCatalogEntry

RUN_ID = RunId("11111111-1111-1111-1111-111111111111")
RUN_B = RunId("22222222-2222-2222-2222-222222222222")
T0 = datetime(2026, 11, 2, tzinfo=timezone.utc)
SERVER = "081c6fe7-e0bd-4aad-9a42-29b8bf073167"
RUNTIME_NAME = f"mcp_{SERVER.replace('-', '_')}_scrape_url"


def _retrieval(run_id: RunId = RUN_ID, document_id: str = "doc-1") -> RetrievalSource:
    return RetrievalSource(
        id="r1", run_id=run_id, tool_call_id=None, collection_name="kb",
        document_id=document_id, chunk_id="c1", score=None, rank_index=1,
        content_preview="발췌", metadata_json={"kb_name": "KB"}, created_at=T0,
    )


def _tool_call(tool_name: str = RUNTIME_NAME, summary: str = '{"content": "결과"}') -> ToolCall:
    return ToolCall(
        id="t1", run_id=RUN_ID, step_id=None, tool_name=tool_name, llm_model_id=None,
        arguments_json=None, result_summary=summary, result_json=None,
        token_usage=None, total_cost_usd=None, latency_ms=None, status="SUCCESS",
        error_text=None, created_at=T0,
    )


def _entry(
    tool_id: str = f"mcp:{SERVER}:scrape_url",
    name: str = "scrape_url",
    source: str = "mcp",
    requires_approval: bool = False,
    category: Optional[str] = None,
) -> ToolCatalogEntry:
    return ToolCatalogEntry(
        id="e1", tool_id=tool_id, source=source, name=name, description="",
        requires_approval=requires_approval, category=category,
    )


def _service(
    retrievals: Optional[dict] = None,
    tool_calls: Optional[dict] = None,
    filenames: Optional[dict] = None,
    catalog: Optional[list] = None,
    max_items: int = 6,
) -> tuple[RunSourcesService, MagicMock, MagicMock, MagicMock, MagicMock]:
    runs = MagicMock()
    runs.find_retrievals_by_runs = AsyncMock(return_value=retrievals or {})
    runs.find_tool_calls_by_runs = AsyncMock(return_value=tool_calls or {})
    documents = MagicMock()
    documents.find_filenames = AsyncMock(return_value=filenames or {})
    tools = MagicMock()
    tools.list_active = AsyncMock(return_value=catalog or [])
    logger = MagicMock()
    service = RunSourcesService(runs, documents, tools, logger, max_items=max_items)
    return service, runs, documents, tools, logger


@pytest.mark.asyncio
class TestBuildForRuns:
    async def test_no_runs_issue_no_query(self) -> None:
        service, runs, *_ = _service()
        assert await service.build_for_runs([], "req") == {}
        runs.find_retrievals_by_runs.assert_not_awaited()

    async def test_groups_items_by_run(self) -> None:
        service, *_ = _service(
            retrievals={RUN_ID.value: [_retrieval()], RUN_B.value: [_retrieval(RUN_B, "doc-2")]},
        )
        result = await service.build_for_runs([RUN_ID, RUN_B], "req")
        assert [i.key for i in result[RUN_ID.value]] == ["doc-1"]
        assert [i.key for i in result[RUN_B.value]] == ["doc-2"]

    async def test_run_without_sources_is_absent(self) -> None:
        service, *_ = _service()
        assert await service.build_for_runs([RUN_ID], "req") == {}

    async def test_filename_is_looked_up_once_for_all_runs(self) -> None:
        service, _, documents, *_ = _service(
            retrievals={RUN_ID.value: [_retrieval()], RUN_B.value: [_retrieval(RUN_B, "doc-2")]},
            filenames={"doc-1": "a.pdf", "doc-2": "b.pdf"},
        )
        result = await service.build_for_runs([RUN_ID, RUN_B], "req")
        assert result[RUN_ID.value][0].label == "a.pdf"
        documents.find_filenames.assert_awaited_once()
        assert sorted(documents.find_filenames.await_args.args[0]) == ["doc-1", "doc-2"]

    async def test_web_rows_do_not_trigger_filename_lookup(self) -> None:
        web = _retrieval()
        web.collection_name = "tavily_web"
        web.document_id = "https://a.example"
        service, _, documents, *_ = _service(retrievals={RUN_ID.value: [web]})
        await service.build_for_runs([RUN_ID], "req")
        documents.find_filenames.assert_not_awaited()

    async def test_runtime_tool_name_matches_catalog_entry(self) -> None:
        service, *_ = _service(
            tool_calls={RUN_ID.value: [_tool_call()]}, catalog=[_entry()],
        )
        item = (await service.build_for_runs([RUN_ID], "req"))[RUN_ID.value][0]
        assert (item.kind, item.label, item.key) == (
            SourceKind.MCP, "scrape_url", f"mcp:{SERVER}:scrape_url",
        )

    async def test_long_tool_name_with_hash_suffix_matches(self) -> None:
        long_tool = "extract_structured_content_from_a_very_long_named_tool"
        runtime = MCPConnectionPolicy.build_tool_name(f"mcp_{SERVER}_{long_tool}")
        service, *_ = _service(
            tool_calls={RUN_ID.value: [_tool_call(tool_name=runtime)]},
            catalog=[_entry(f"mcp:{SERVER}:{long_tool}", long_tool)],
        )
        item = (await service.build_for_runs([RUN_ID], "req"))[RUN_ID.value][0]
        assert item.label == long_tool

    async def test_requires_approval_flag_reaches_policy(self) -> None:
        service, *_ = _service(
            tool_calls={RUN_ID.value: [_tool_call()]},
            catalog=[_entry(requires_approval=True)],
        )
        assert await service.build_for_runs([RUN_ID], "req") == {}

    async def test_server_level_and_internal_entries_are_ignored(self) -> None:
        service, *_ = _service(
            tool_calls={RUN_ID.value: [_tool_call()]},
            catalog=[_entry(f"mcp_{SERVER}"), _entry("tavily_search", source="internal")],
        )
        assert await service.build_for_runs([RUN_ID], "req") == {}

    async def test_catalog_is_not_read_without_mcp_calls(self) -> None:
        service, _, _, tools, _ = _service(
            tool_calls={RUN_ID.value: [_tool_call(tool_name="tavily_search")]},
        )
        await service.build_for_runs([RUN_ID], "req")
        tools.list_active.assert_not_awaited()

    async def test_max_items_is_applied(self) -> None:
        rows = [_retrieval(document_id=f"d{n}") for n in range(4)]
        for n, row in enumerate(rows):
            row.id = f"r{n}"
        service, *_ = _service(retrievals={RUN_ID.value: rows}, max_items=2)
        assert len((await service.build_for_runs([RUN_ID], "req"))[RUN_ID.value]) == 2


@pytest.mark.asyncio
class TestFailureAbsorption:
    async def test_evidence_failure_returns_empty_and_logs_exception(self) -> None:
        service, runs, _, _, logger = _service()
        error = RuntimeError("db down")
        runs.find_retrievals_by_runs.side_effect = error
        assert await service.build_for_runs([RUN_ID], "req") == {}
        assert logger.warning.call_args.kwargs["exception"] is error

    async def test_filename_failure_keeps_fallback_label(self) -> None:
        service, _, documents, _, logger = _service(
            retrievals={RUN_ID.value: [_retrieval()]},
        )
        error = RuntimeError("x")
        documents.find_filenames.side_effect = error
        result = await service.build_for_runs([RUN_ID], "req")
        assert result[RUN_ID.value][0].label == "KB"
        assert logger.warning.call_args.kwargs["exception"] is error

    async def test_catalog_failure_drops_only_mcp_chips(self) -> None:
        service, _, _, tools, logger = _service(
            retrievals={RUN_ID.value: [_retrieval()]},
            tool_calls={RUN_ID.value: [_tool_call()]},
        )
        error = RuntimeError("x")
        tools.list_active.side_effect = error
        result = await service.build_for_runs([RUN_ID], "req")
        assert [i.kind for i in result[RUN_ID.value]] == [SourceKind.DOCUMENT]
        assert logger.warning.call_args.kwargs["exception"] is error
