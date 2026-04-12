"""Application tools tests for general_chat (AsyncMock)."""
import time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.general_chat.tools import MCPToolCache, ChatToolBuilder
from src.domain.general_chat.policies import ChatAgentPolicy


# ── MCPToolCache ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_cache_miss_calls_load():
    """TC-1: 캐시 미스 → load_mcp_use_case.execute 호출."""
    MCPToolCache._cache.clear()
    mock_use_case = AsyncMock()
    mock_use_case.execute.return_value = [MagicMock(), MagicMock()]

    tools = await MCPToolCache.get_or_load(mock_use_case, request_id="req-1", ttl=600)

    mock_use_case.execute.assert_called_once_with("req-1")
    assert len(tools) == 2


@pytest.mark.asyncio
async def test_mcp_cache_hit_skips_load():
    """TC-2: 캐시 히트 → load_mcp_use_case.execute 미호출."""
    MCPToolCache._cache.clear()
    fake_tools = [MagicMock()]
    MCPToolCache._cache["__all__"] = (fake_tools, time.time() + 600)

    mock_use_case = AsyncMock()
    tools = await MCPToolCache.get_or_load(mock_use_case, request_id="req-1", ttl=600)

    mock_use_case.execute.assert_not_called()
    assert tools == fake_tools


@pytest.mark.asyncio
async def test_mcp_cache_ttl_expired_reloads():
    """TC-3: TTL 만료 → 재로드."""
    MCPToolCache._cache.clear()
    fake_old = [MagicMock()]
    MCPToolCache._cache["__all__"] = (fake_old, time.time() - 1)  # 이미 만료

    new_tools = [MagicMock(), MagicMock()]
    mock_use_case = AsyncMock()
    mock_use_case.execute.return_value = new_tools

    tools = await MCPToolCache.get_or_load(mock_use_case, request_id="req-1", ttl=600)

    mock_use_case.execute.assert_called_once()
    assert tools == new_tools


# ── ChatToolBuilder ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_tool_builder_returns_three_tool_types():
    """TC-4: ChatToolBuilder.build() → Tavily, InternalDoc, MCP 3종 반환."""
    MCPToolCache._cache.clear()

    tavily = MagicMock()
    tavily.name = "tavily_search"
    internal = MagicMock()
    internal.name = "internal_document_search"
    mcp_tool = MagicMock()
    mcp_tool.name = "mcp_tool_a"

    mock_use_case = AsyncMock()
    mock_use_case.execute.return_value = [mcp_tool]

    builder = ChatToolBuilder(
        tavily_tool=tavily,
        internal_doc_tool=internal,
        mcp_cache=MCPToolCache,
        load_mcp_use_case=mock_use_case,
    )
    tools = await builder.build(top_k=5, request_id="req-1")

    names = [t.name for t in tools]
    assert "tavily_search" in names
    assert "internal_document_search" in names
    assert "mcp_tool_a" in names


@pytest.mark.asyncio
async def test_chat_tool_builder_no_mcp_returns_two_tools():
    """TC-5: MCP 도구 0개 → Tavily + InternalDoc 2개만 반환."""
    MCPToolCache._cache.clear()

    tavily = MagicMock()
    tavily.name = "tavily_search"
    internal = MagicMock()
    internal.name = "internal_document_search"

    mock_use_case = AsyncMock()
    mock_use_case.execute.return_value = []

    builder = ChatToolBuilder(
        tavily_tool=tavily,
        internal_doc_tool=internal,
        mcp_cache=MCPToolCache,
        load_mcp_use_case=mock_use_case,
    )
    tools = await builder.build(top_k=5, request_id="req-1")

    assert len(tools) == 2


@pytest.mark.asyncio
async def test_internal_doc_tool_top_k_passed():
    """TC-6: InternalDocumentSearchTool에 top_k 파라미터 전달 검증."""
    MCPToolCache._cache.clear()

    tavily = MagicMock()
    tavily.name = "tavily_search"

    # InternalDocumentSearchTool은 top_k 속성으로 생성됨
    internal = MagicMock()
    internal.name = "internal_document_search"
    internal.top_k = 5

    mock_use_case = AsyncMock()
    mock_use_case.execute.return_value = []

    builder = ChatToolBuilder(
        tavily_tool=tavily,
        internal_doc_tool=internal,
        mcp_cache=MCPToolCache,
        load_mcp_use_case=mock_use_case,
    )
    tools = await builder.build(top_k=10, request_id="req-1")

    # build(top_k=10)이 InternalDocumentSearchTool의 top_k를 10으로 설정하는지 확인
    internal_tool = next(t for t in tools if t.name == "internal_document_search")
    assert internal_tool.top_k == 10


@pytest.mark.asyncio
async def test_mcp_load_exception_logs_warning_returns_empty():
    """TC-7: MCP 로드 예외 시 WARNING 로그 + 빈 리스트 반환."""
    MCPToolCache._cache.clear()

    mock_use_case = AsyncMock()
    mock_use_case.execute.side_effect = Exception("MCP 연결 실패")

    mock_logger = MagicMock()

    tools = await MCPToolCache.get_or_load(
        mock_use_case, request_id="req-1", ttl=600, logger=mock_logger
    )

    assert tools == []
    mock_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_chat_tool_builder_tool_order():
    """TC-8: 도구 순서 = Tavily → InternalDoc → MCP."""
    MCPToolCache._cache.clear()

    tavily = MagicMock()
    tavily.name = "tavily_search"
    internal = MagicMock()
    internal.name = "internal_document_search"
    mcp_tool = MagicMock()
    mcp_tool.name = "mcp_tool_a"

    mock_use_case = AsyncMock()
    mock_use_case.execute.return_value = [mcp_tool]

    builder = ChatToolBuilder(
        tavily_tool=tavily,
        internal_doc_tool=internal,
        mcp_cache=MCPToolCache,
        load_mcp_use_case=mock_use_case,
    )
    tools = await builder.build(top_k=5, request_id="req-1")

    assert tools[0].name == "tavily_search"
    assert tools[1].name == "internal_document_search"
    assert tools[2].name == "mcp_tool_a"
