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
        assert tool.name == "internal_document_search"

    def test_default_uses_plain_hybrid_search(self):
        logger = MagicMock()
        hybrid = MagicMock()
        wiki = MagicMock()
        factory = ToolFactory(
            logger=logger, hybrid_search_use_case=hybrid, wiki_search=wiki
        )
        tool = factory.create("internal_document_search")  # use_wiki_first 기본 False
        assert tool.hybrid_search_use_case is hybrid

    def test_use_wiki_first_selects_wiki_adapter(self):
        logger = MagicMock()
        hybrid = MagicMock()
        wiki = MagicMock()
        factory = ToolFactory(
            logger=logger, hybrid_search_use_case=hybrid, wiki_search=wiki
        )
        tool = factory.create(
            "internal_document_search", tool_config={"use_wiki_first": True}
        )
        assert tool.hybrid_search_use_case is wiki

    def test_use_wiki_first_without_adapter_falls_back_to_hybrid(self):
        logger = MagicMock()
        hybrid = MagicMock()
        factory = ToolFactory(
            logger=logger, hybrid_search_use_case=hybrid, wiki_search=None
        )
        tool = factory.create(
            "internal_document_search", tool_config={"use_wiki_first": True}
        )
        assert tool.hybrid_search_use_case is hybrid

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
        import re
        assert re.match(r"^[a-zA-Z0-9_-]+$", tool.name)
        assert tool.description == "금융 관련 내부 문서를 검색합니다."
        assert tool.top_k == 10
        assert tool.search_mode == "vector_only"
        assert tool.metadata_filter == {"department": "finance"}

    def test_create_with_ascii_tool_name_preserved(self):
        factory = _make_factory()
        config = {"tool_name": "finance_doc_search"}
        tool = factory.create("internal_document_search", tool_config=config)
        assert tool.name == "finance_doc_search"

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


class TestToolFactoryRoutedSearch:
    """rag-routed-integration D2 — routed getter 주입·전달."""

    def test_routed_getter_and_flag_forwarded(self):
        getter = lambda: MagicMock()  # noqa: E731
        factory = ToolFactory(
            logger=MagicMock(),
            hybrid_search_use_case=MagicMock(),
            routed_retrieval_getter=getter,
        )
        tool = factory.create(
            "internal_document_search",
            tool_config={"use_routed_search": True},
        )
        assert tool.use_routed_search is True
        assert tool.routed_retrieval_getter is getter

    def test_default_config_disables_routed(self):
        tool = _make_factory().create("internal_document_search")
        assert tool.use_routed_search is False
        assert tool.routed_retrieval_getter is None

    def test_legacy_config_without_field_restores_false(self):
        """기존 저장 config(필드 부재) 하위호환 (D1)."""
        tool = _make_factory().create(
            "internal_document_search",
            tool_config={"top_k": 7, "search_mode": "vector_only"},
        )
        assert tool.use_routed_search is False
        assert tool.search_mode == "vector_only"


class TestToolFactoryKbFilter:
    """kb-rag-filter D6 — kb_id를 metadata_filter에 병합."""

    def test_kb_id_merged_into_metadata_filter(self):
        tool = _make_factory().create(
            "internal_document_search",
            tool_config={"kb_id": "kb-uuid-001"},
        )
        assert tool.metadata_filter == {"kb_id": "kb-uuid-001"}

    def test_kb_id_merges_with_existing_filters(self):
        tool = _make_factory().create(
            "internal_document_search",
            tool_config={
                "kb_id": "kb-uuid-001",
                "metadata_filter": {"department": "finance"},
            },
        )
        assert tool.metadata_filter == {
            "department": "finance",
            "kb_id": "kb-uuid-001",
        }

    def test_first_class_kb_id_overrides_manual_filter_key(self):
        """D2: metadata_filter의 수동 kb_id 키보다 필드가 우선."""
        tool = _make_factory().create(
            "internal_document_search",
            tool_config={
                "kb_id": "kb-field",
                "metadata_filter": {"kb_id": "kb-manual"},
            },
        )
        assert tool.metadata_filter["kb_id"] == "kb-field"

    def test_without_kb_id_filter_unchanged(self):
        """FR-06: kb_id 미설정 시 기존 동작 그대로."""
        tool = _make_factory().create(
            "internal_document_search",
            tool_config={"metadata_filter": {"department": "finance"}},
        )
        assert tool.metadata_filter == {"department": "finance"}

    def test_legacy_config_without_kb_id_restores_none(self):
        tool = _make_factory().create(
            "internal_document_search",
            tool_config={"top_k": 7},
        )
        assert tool.metadata_filter == {}


class TestToolFactoryScoreThreshold:
    """벡터 코사인 컷오프 임계값 주입 (에이전트값 우선 + 전역 fallback)."""

    def test_uses_agent_threshold_when_set(self, monkeypatch):
        monkeypatch.setattr(
            "src.config.settings.rag_vector_score_threshold", 0.1
        )
        factory = _make_factory()
        tool = factory.create(
            "internal_document_search", tool_config={"score_threshold": 0.4}
        )
        assert tool.score_threshold == 0.4

    def test_falls_back_to_global_when_none(self, monkeypatch):
        monkeypatch.setattr(
            "src.config.settings.rag_vector_score_threshold", 0.25
        )
        factory = _make_factory()
        tool = factory.create("internal_document_search")
        assert tool.score_threshold == 0.25

    def test_explicit_zero_overrides_global(self, monkeypatch):
        monkeypatch.setattr(
            "src.config.settings.rag_vector_score_threshold", 0.25
        )
        factory = _make_factory()
        tool = factory.create(
            "internal_document_search", tool_config={"score_threshold": 0.0}
        )
        assert tool.score_threshold == 0.0

    def test_default_global_zero_is_disabled(self):
        factory = _make_factory()
        tool = factory.create("internal_document_search")
        assert tool.score_threshold == 0.0


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
