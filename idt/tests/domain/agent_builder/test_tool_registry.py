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

    def test_get_all_tools_returns_all_four(self):
        tools = get_all_tools()
        assert len(tools) == 4

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
