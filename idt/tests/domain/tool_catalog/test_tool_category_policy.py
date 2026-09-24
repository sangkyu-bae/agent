"""ToolCategoryPolicy 단위 테스트.

Design Ref: mcp-tool-category-routing §3.1 (FR-02) / §5 D-04
  - 카테고리 허용값은 search/collect/analysis/action 4종 + None(미분류)
  - collect는 '도구 1회 호출'이 정의되는 단일 도구 참조에만 지정할 수 있다.
    서버 단위 레거시(mcp_{srv})는 create_all_async가 서버 도구 전체를
    바인딩하므로 단일샷 계약이 성립하지 않는다.
"""
import pytest

from src.domain.tool_catalog.policies import ToolCategoryPolicy


class TestToolCategoryPolicyValidate:
    @pytest.mark.parametrize(
        "category",
        ["search", "collect", "analysis", "action"],
    )
    def test_allows_every_defined_category(self, category):
        ToolCategoryPolicy.validate(category)

    def test_allows_none_as_unclassified(self):
        """FR-14: None은 미분류 — 기존 react 경로를 의미하므로 유효하다."""
        ToolCategoryPolicy.validate(None)

    @pytest.mark.parametrize(
        "category",
        ["generate", "SEARCH", "", "  ", "collect ", "unknown"],
    )
    def test_rejects_value_outside_allowed_set(self, category):
        with pytest.raises(ValueError):
            ToolCategoryPolicy.validate(category)

    def test_allowed_set_is_exactly_four(self):
        assert ToolCategoryPolicy.ALLOWED == frozenset(
            {"search", "collect", "analysis", "action"}
        )


class TestToolCategoryPolicyAssignable:
    def test_collect_allowed_on_catalog_format_mcp_tool(self):
        """D-04: mcp:{server}:{tool}은 도구 1개를 특정하므로 collect 가능."""
        ToolCategoryPolicy.assert_assignable(
            "collect", "mcp:3f2a1b4c-0000-1111-2222-333344445555:scrape"
        )

    def test_collect_allowed_on_internal_tool(self):
        ToolCategoryPolicy.assert_assignable("collect", "tavily_search")

    def test_collect_rejected_on_server_level_legacy_tool(self):
        """D-04: mcp_{server}는 도구가 여럿이라 '1회 호출'이 정의되지 않는다."""
        with pytest.raises(ValueError) as exc:
            ToolCategoryPolicy.assert_assignable("collect", "mcp_server-1")
        assert "collect" in str(exc.value)

    def test_search_and_analysis_allowed_on_server_level_tool(self):
        """제약은 단일샷 계열(collect·action) 한정 — 나머지는 서버 단위에도 지정 가능."""
        ToolCategoryPolicy.assert_assignable("search", "mcp_server-1")
        ToolCategoryPolicy.assert_assignable("analysis", "mcp_server-1")

    def test_action_rejected_on_server_level_legacy_tool(self):
        """action-category-compose-node FR-03: action도 '도구 1회 호출' 계약이라
        서버 단위 참조에는 지정할 수 없다 (collect D-04 확장)."""
        with pytest.raises(ValueError) as exc:
            ToolCategoryPolicy.assert_assignable("action", "mcp_server-1")
        assert "action" in str(exc.value)

    def test_action_allowed_on_catalog_format_mcp_tool(self):
        ToolCategoryPolicy.assert_assignable(
            "action", "mcp:3f2a1b4c-0000-1111-2222-333344445555:send_mail"
        )

    def test_action_allowed_on_internal_tool(self):
        ToolCategoryPolicy.assert_assignable("action", "python_code_executor")

    def test_none_allowed_on_server_level_tool(self):
        ToolCategoryPolicy.assert_assignable(None, "mcp_server-1")

    def test_invalid_category_rejected_before_assignability(self):
        with pytest.raises(ValueError):
            ToolCategoryPolicy.assert_assignable("generate", "tavily_search")


class TestToolCategoryPolicyToolCallLimit:
    def test_none_is_allowed(self):
        ToolCategoryPolicy.validate_tool_call_limit(None)

    @pytest.mark.parametrize("limit", [1, 2, 5, 20])
    def test_in_range_values_allowed(self, limit):
        ToolCategoryPolicy.validate_tool_call_limit(limit)

    @pytest.mark.parametrize("limit", [0, -1, 21, 1000])
    def test_out_of_range_rejected(self, limit):
        with pytest.raises(ValueError):
            ToolCategoryPolicy.validate_tool_call_limit(limit)

    def test_bool_is_not_accepted_as_int(self):
        """bool은 int의 하위형이지만 호출 상한 값으로는 의미가 없다."""
        with pytest.raises(ValueError):
            ToolCategoryPolicy.validate_tool_call_limit(True)
