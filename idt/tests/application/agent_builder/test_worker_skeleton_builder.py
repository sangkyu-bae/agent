"""WorkerSkeletonBuilder — agent-update-tool-editing D §2.3 / §9.4.

CreateAgentUseCase 의 워커 빌드 private 메서드를 행위보존 추출한 공용 모듈.
create/update 두 경로가 도구 ID 정규화·MCP 해석·빌트인 주입 규칙을 공유한다.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.application.agent_builder.schemas import RagToolConfigRequest
from src.application.agent_builder.worker_skeleton_builder import (
    WorkerSkeletonBuilder,
    make_worker_id,
    normalize_tool_id,
)
from src.domain.agent_builder.schemas import WorkerDefinition
from src.domain.mcp_registry.schemas import MCPServerRegistration, MCPTransportType
from src.domain.tool_catalog.entity import ToolCatalogEntry

MCP_SERVER_ID = "11111111-2222-3333-4444-555555555555"


def _mcp_registration(is_active: bool = True) -> MCPServerRegistration:
    now = datetime.now(timezone.utc)
    return MCPServerRegistration(
        id=MCP_SERVER_ID,
        user_id="user-1",
        name="테스트 MCP 서버",
        description="MCP 서버 설명",
        endpoint="https://mcp.example.com",
        transport=MCPTransportType.STREAMABLE_HTTP,
        input_schema=None,
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )


def _catalog_entry(tool_id: str, is_builtin: bool = True) -> ToolCatalogEntry:
    return ToolCatalogEntry(
        id=f"tc-{tool_id}",
        tool_id=tool_id,
        source="mcp" if tool_id.startswith("mcp:") else "internal",
        name=tool_id,
        description=f"desc-{tool_id}",
        mcp_server_id=tool_id.split(":")[1] if tool_id.startswith("mcp:") else None,
        is_active=True,
        is_builtin=is_builtin,
    )


def _builder(
    mcp_active: bool = True,
    with_mcp_repo: bool = True,
    builtins: list[ToolCatalogEntry] | None = None,
    with_catalog_repo: bool = True,
) -> WorkerSkeletonBuilder:
    mcp_server_repo = None
    if with_mcp_repo:
        mcp_server_repo = MagicMock()
        mcp_server_repo.find_by_id = AsyncMock(
            return_value=_mcp_registration(mcp_active)
        )

    tool_catalog_repo = None
    if with_catalog_repo:
        tool_catalog_repo = MagicMock()
        tool_catalog_repo.list_builtin = AsyncMock(return_value=builtins or [])
        tool_catalog_repo.find_by_tool_id = AsyncMock(return_value=None)

    return WorkerSkeletonBuilder(
        logger=MagicMock(),
        mcp_server_repo=mcp_server_repo,
        tool_catalog_repo=tool_catalog_repo,
    )


# --- 순수 함수 -----------------------------------------------------------


def test_normalize_tool_id_strips_internal_prefix_only():
    assert normalize_tool_id("internal:tavily_search") == "tavily_search"
    assert normalize_tool_id("tavily_search") == "tavily_search"


def test_normalize_tool_id_keeps_mcp_notation_intact():
    """MCP는 개별 도구 단위를 그대로 저장한다 (서버 단위로 접으면 선택 소실)."""
    assert normalize_tool_id(f"mcp:{MCP_SERVER_ID}:fetch") == (
        f"mcp:{MCP_SERVER_ID}:fetch"
    )
    assert normalize_tool_id(f"mcp_{MCP_SERVER_ID}") == f"mcp_{MCP_SERVER_ID}"


def test_make_worker_id_sanitizes_colons():
    """worker_id는 LangGraph 노드명이라 콜론을 못 쓴다."""
    assert make_worker_id("tavily_search") == "tavily_search_worker"
    assert ":" not in make_worker_id(f"mcp:{MCP_SERVER_ID}:fetch")


# --- tool_ids 경로 -------------------------------------------------------


@pytest.mark.asyncio
async def test_build_from_tool_ids_creates_workers_in_order():
    skeleton = await _builder().build_from_tool_ids(
        ["internal:tavily_search", "internal:presentation_generator"], None, "req-1"
    )

    assert [w.tool_id for w in skeleton.workers] == [
        "tavily_search", "presentation_generator",
    ]
    assert [w.sort_order for w in skeleton.workers] == [0, 1]
    assert [w.worker_id for w in skeleton.workers] == [
        "tavily_search_worker", "presentation_generator_worker",
    ]
    assert skeleton.flow_hint == "tavily_search → presentation_generator"


@pytest.mark.asyncio
async def test_build_from_tool_ids_dedupes_identical_ids():
    skeleton = await _builder().build_from_tool_ids(
        ["internal:tavily_search", "tavily_search"], None, "req-1"
    )

    assert len(skeleton.workers) == 1


@pytest.mark.asyncio
async def test_build_from_tool_ids_injects_matching_config():
    configs = {
        "internal:internal_document_search": RagToolConfigRequest(top_k=7),
    }
    skeleton = await _builder().build_from_tool_ids(
        ["internal:internal_document_search", "internal:tavily_search"],
        configs,
        "req-1",
    )

    assert skeleton.workers[0].tool_config["top_k"] == 7
    assert skeleton.workers[1].tool_config is None


@pytest.mark.asyncio
async def test_build_from_tool_ids_resolves_mcp_description():
    skeleton = await _builder().build_from_tool_ids(
        [f"mcp:{MCP_SERVER_ID}:fetch"], None, "req-1"
    )

    assert skeleton.workers[0].tool_id == f"mcp:{MCP_SERVER_ID}:fetch"
    assert "fetch" in skeleton.workers[0].description


@pytest.mark.asyncio
async def test_build_from_tool_ids_rejects_inactive_mcp_server():
    with pytest.raises(ValueError, match="비활성화"):
        await _builder(mcp_active=False).build_from_tool_ids(
            [f"mcp:{MCP_SERVER_ID}:fetch"], None, "req-1"
        )


@pytest.mark.asyncio
async def test_build_from_tool_ids_rejects_mcp_without_repo():
    with pytest.raises(ValueError):
        await _builder(with_mcp_repo=False).build_from_tool_ids(
            [f"mcp:{MCP_SERVER_ID}:fetch"], None, "req-1"
        )


@pytest.mark.asyncio
async def test_build_from_tool_ids_rejects_unknown_internal_tool():
    with pytest.raises(ValueError):
        await _builder().build_from_tool_ids(
            ["internal:no_such_tool"], None, "req-1"
        )


# --- tool_configs 경로 ---------------------------------------------------


def test_build_from_configs_creates_workers_with_config():
    skeleton = _builder().build_from_configs(
        {"internal:internal_document_search": RagToolConfigRequest(top_k=3)},
        "req-1",
    )

    assert skeleton.workers[0].tool_id == "internal_document_search"
    assert skeleton.workers[0].worker_id == "internal_document_search_worker"
    assert skeleton.workers[0].tool_config["top_k"] == 3


# --- 빌트인 주입 ---------------------------------------------------------


@pytest.mark.asyncio
async def test_build_builtin_workers_injects_active_builtins():
    builder = _builder(builtins=[_catalog_entry("internal:wiki_read")])

    workers = await builder.build_builtin_workers([], None, "req-1")

    assert [w.tool_id for w in workers] == ["wiki_read"]
    assert workers[0].worker_id == "wiki_read_worker"


@pytest.mark.asyncio
async def test_build_builtin_workers_skips_already_selected():
    builder = _builder(builtins=[_catalog_entry("internal:wiki_read")])
    existing = [
        WorkerDefinition(
            tool_id="wiki_read", worker_id="wiki_read_worker", description="d"
        )
    ]

    workers = await builder.build_builtin_workers(existing, None, "req-1")

    assert workers == []


@pytest.mark.asyncio
async def test_build_builtin_workers_honors_exclude_list():
    builder = _builder(builtins=[_catalog_entry("internal:wiki_read")])

    workers = await builder.build_builtin_workers(
        [], ["internal:wiki_read"], "req-1"
    )

    assert workers == []


@pytest.mark.asyncio
async def test_build_builtin_workers_skips_unresolvable_tool_instead_of_failing():
    """빌트인 잔재(비활성 MCP 등)가 생성 자체를 실패시키면 안 된다 (FR-07)."""
    builder = _builder(
        mcp_active=False, builtins=[_catalog_entry(f"mcp:{MCP_SERVER_ID}:fetch")]
    )

    workers = await builder.build_builtin_workers([], None, "req-1")

    assert workers == []


@pytest.mark.asyncio
async def test_build_builtin_workers_without_catalog_repo_returns_empty():
    builder = _builder(with_catalog_repo=False)

    assert await builder.build_builtin_workers([], None, "req-1") == []


@pytest.mark.asyncio
async def test_build_builtin_workers_sort_order_continues_after_existing():
    builder = _builder(builtins=[_catalog_entry("internal:wiki_read")])
    existing = [
        WorkerDefinition(tool_id="a", worker_id="a_worker", description="d"),
        WorkerDefinition(tool_id="b", worker_id="b_worker", description="d"),
    ]

    workers = await builder.build_builtin_workers(existing, None, "req-1")

    assert workers[0].sort_order == 2
