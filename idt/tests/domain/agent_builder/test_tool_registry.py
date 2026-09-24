"""TOOL_REGISTRY 단위 테스트 — mock 금지."""
import pytest
from src.domain.agent_builder.tool_registry import (
    TOOL_REGISTRY,
    get_all_tools,
    get_tool_meta,
)

EXPECTED_TOOL_IDS = {
    "internal_document_search",
    "tavily_search",
    "excel_export",
    "python_code_executor",
    "data_analysis",
    "document_extractor",
    "document_generator",
    "presentation_generator",
    "wiki_read",
    "wiki_list",
}


class TestToolRegistry:
    def test_registry_contains_all_expected_tools(self):
        assert set(TOOL_REGISTRY.keys()) == EXPECTED_TOOL_IDS

    def test_each_tool_has_non_empty_name(self):
        for meta in TOOL_REGISTRY.values():
            assert meta.name, f"{meta.tool_id} name이 비어 있음"

    def test_each_tool_has_non_empty_description(self):
        for meta in TOOL_REGISTRY.values():
            assert meta.description, f"{meta.tool_id} description이 비어 있음"

    def test_tool_id_matches_registry_key(self):
        for key, meta in TOOL_REGISTRY.items():
            assert meta.tool_id == key

    def test_get_tool_meta_returns_correct_meta(self):
        meta = get_tool_meta("tavily_search")
        assert meta.tool_id == "tavily_search"
        assert meta.name == "Tavily 웹 검색"

    def test_get_tool_meta_raises_for_unknown_tool(self):
        with pytest.raises(ValueError, match="Unknown tool_id"):
            get_tool_meta("non_existent_tool")

    def test_get_all_tools_returns_all_registered(self):
        tools = get_all_tools()
        assert len(tools) == len(EXPECTED_TOOL_IDS)

    def test_get_all_tools_sorted_by_tool_id(self):
        tools = get_all_tools()
        tool_ids = [t.tool_id for t in tools]
        assert tool_ids == sorted(tool_ids)

    def test_tavily_requires_api_key_env(self):
        meta = get_tool_meta("tavily_search")
        assert "TAVILY_API_KEY" in meta.requires_env

    def test_excel_export_requires_no_env(self):
        meta = get_tool_meta("excel_export")
        assert meta.requires_env == []

    def test_excel_export_description_guides_supervisor_routing(self):
        # excel-generator-node FR-10 / Plan Risk #3: 슈퍼바이저 라우팅 문구 회귀 방지
        desc = get_tool_meta("excel_export").description
        assert "다운로드" in desc
        assert "수집" in desc


class TestToolRegistryCategory:
    def test_internal_document_search_is_search(self):
        meta = get_tool_meta("internal_document_search")
        assert meta.category == "search"

    def test_tavily_search_is_search(self):
        meta = get_tool_meta("tavily_search")
        assert meta.category == "search"

    def test_excel_export_is_unclassified(self):
        """action-category-compose-node D-01: 명시 지정 없음 → None(react/전용 노드)."""
        meta = get_tool_meta("excel_export")
        assert meta.category is None

    def test_python_code_executor_is_unclassified(self):
        meta = get_tool_meta("python_code_executor")
        assert meta.category is None

    def test_data_analysis_is_analysis(self):
        meta = get_tool_meta("data_analysis")
        assert meta.category == "analysis"

    def test_document_extractor_is_unclassified(self):
        """document-template-extractor GA1: env 불필요. 카테고리는 미지정(None) —
        전용 생성 노드는 카테고리 해석 전에 분기되므로 값이 없어야 한다."""
        meta = get_tool_meta("document_extractor")
        assert meta.category is None
        assert meta.requires_env == []

    def test_wiki_read_is_not_search_or_analysis(self):
        """wiki-agentic-navigation D6: search/analysis 미지정 → react agent 워커 경로.

        category='search'면 search 파이프라인 노드로, 'analysis'면 분석 노드로
        분기되므로 wiki_read는 어느 쪽도 아니어야 한다.
        """
        meta = get_tool_meta("wiki_read")
        assert meta.category not in ("search", "analysis")
        assert meta.requires_env == []

    def test_wiki_list_is_not_search_or_analysis(self):
        """wiki-folder-summaries D4: wiki_read와 동일하게 react agent 워커 경로."""
        meta = get_tool_meta("wiki_list")
        assert meta.category not in ("search", "analysis")
        assert meta.requires_env == []
