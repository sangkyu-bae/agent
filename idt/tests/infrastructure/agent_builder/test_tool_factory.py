"""ToolFactory 단위 테스트 — Mock DI 사용."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.tools import BaseTool

from src.infrastructure.agent_builder.tool_factory import ToolFactory


def _make_factory(tavily_api_key: str = "test-key", mcp_tool_loader=None) -> ToolFactory:
    logger = MagicMock()
    hybrid_search = MagicMock()
    return ToolFactory(
        logger=logger,
        hybrid_search_use_case=hybrid_search,
        tavily_api_key=tavily_api_key,
        mcp_tool_loader=mcp_tool_loader,
    )


class TestToolFactory:
    def test_create_excel_export_tool(self):
        factory = _make_factory()
        tool = factory.create("excel_export")
        assert isinstance(tool, BaseTool)
        assert tool.name == "excel_export"

    def test_create_python_code_executor_tool(self):
        factory = _make_factory()
        tool = factory.create("python_code_executor")
        assert isinstance(tool, BaseTool)
        assert tool.name == "python_code_executor"

    def test_create_tavily_search_tool(self):
        factory = _make_factory(tavily_api_key="test-key")
        tool = factory.create("tavily_search")
        assert isinstance(tool, BaseTool)
        assert tool.name == "tavily_search"

    def test_create_internal_document_search_tool(self):
        factory = _make_factory()
        tool = factory.create("internal_document_search")
        assert isinstance(tool, BaseTool)
        assert tool.name == "내부 문서 검색"

    def test_create_unknown_tool_raises(self):
        factory = _make_factory()
        with pytest.raises(ValueError, match="Unknown tool_id"):
            factory.create("unknown_tool")


class TestToolFactoryRagConfig:
    def test_create_with_rag_config_applies_settings(self):
        factory = _make_factory()
        config = {
            "top_k": 10,
            "search_mode": "vector_only",
            "metadata_filter": {"department": "finance"},
            "tool_name": "금융 문서 검색",
            "tool_description": "금융 관련 내부 문서를 검색합니다.",
        }
        tool = factory.create("internal_document_search", tool_config=config)
        assert tool.name == "금융 문서 검색"
        assert tool.description == "금융 관련 내부 문서를 검색합니다."
        assert tool.top_k == 10
        assert tool.search_mode == "vector_only"
        assert tool.metadata_filter == {"department": "finance"}

    def test_create_without_config_uses_defaults(self):
        factory = _make_factory()
        tool = factory.create("internal_document_search")
        assert tool.top_k == 5
        assert tool.search_mode == "hybrid"
        assert tool.metadata_filter == {}

    def test_create_with_none_config_uses_defaults(self):
        factory = _make_factory()
        tool = factory.create("internal_document_search", tool_config=None)
        assert tool.top_k == 5

    def test_create_with_partial_config_merges_defaults(self):
        factory = _make_factory()
        tool = factory.create(
            "internal_document_search", tool_config={"top_k": 15}
        )
        assert tool.top_k == 15
        assert tool.search_mode == "hybrid"

    def test_parse_rag_config_invalid_raises(self):
        factory = _make_factory()
        with pytest.raises(ValueError):
            factory.create(
                "internal_document_search",
                tool_config={"top_k": 999},
            )

    def test_non_rag_tool_ignores_config(self):
        factory = _make_factory()
        tool = factory.create("excel_export", tool_config={"top_k": 10})
        assert tool.name == "excel_export"


class TestToolFactoryMCPRouting:

    @pytest.mark.asyncio
    async def test_create_async_routes_mcp_prefix_to_loader(self):
        mock_tool = MagicMock(spec=BaseTool)
        mock_loader = MagicMock()
        mock_loader.load_by_tool_id = AsyncMock(return_value=[mock_tool])
        mock_repo = MagicMock()

        factory = _make_factory(mcp_tool_loader=mock_loader)
        result = await factory.create_async(
            tool_id="mcp_uuid-001",
            request_id="req-001",
            mcp_repository=mock_repo,
        )

        assert result is mock_tool
        mock_loader.load_by_tool_id.assert_called_once_with(
            tool_id="mcp_uuid-001",
            repository=mock_repo,
            request_id="req-001",
        )

    @pytest.mark.asyncio
    async def test_create_async_raises_when_mcp_tool_not_found(self):
        mock_loader = MagicMock()
        mock_loader.load_by_tool_id = AsyncMock(return_value=[])
        mock_repo = MagicMock()

        factory = _make_factory(mcp_tool_loader=mock_loader)
        with pytest.raises(ValueError, match="mcp_missing"):
            await factory.create_async(
                tool_id="mcp_missing",
                request_id="req-001",
                mcp_repository=mock_repo,
            )

    @pytest.mark.asyncio
    async def test_create_async_raises_when_no_loader_for_mcp(self):
        factory = _make_factory(mcp_tool_loader=None)
        with pytest.raises(ValueError, match="MCPToolLoader"):
            await factory.create_async(
                tool_id="mcp_uuid-001",
                request_id="req-001",
                mcp_repository=MagicMock(),
            )
