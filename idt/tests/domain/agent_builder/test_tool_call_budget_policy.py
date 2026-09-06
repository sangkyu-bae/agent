"""ToolCallBudgetPolicy 단위 테스트.

Design Ref: mcp-tool-category-routing §5 D-05 (FR-10)
  미분류(react) 워커의 도구 호출 예산. 기본 2회인 근거는 자가교정 1회다 —
  1차 호출이 ToolArgumentPolicy에 차단되면 워커가 차단 메시지를 받아
  스스로 고칠 기회가 정확히 한 번 필요하다.

  소비자는 module-3(workflow_compiler)이며, 이 파일은 해석 규칙만 고정한다.
"""
import pytest

from src.domain.agent_builder.policies import ToolCallBudgetPolicy


class TestToolCallBudgetResolve:
    def test_none_uses_default(self):
        assert ToolCallBudgetPolicy.resolve(None) == 2

    def test_default_is_two_for_self_correction(self):
        """기본값이 2인 이유가 바뀌면 이 테스트가 먼저 깨져야 한다."""
        assert ToolCallBudgetPolicy.DEFAULT_RUN_LIMIT == 2

    @pytest.mark.parametrize("value", [1, 2, 3, 10, 20])
    def test_in_range_value_is_used_as_is(self, value):
        assert ToolCallBudgetPolicy.resolve(value) == value

    @pytest.mark.parametrize("value,expected", [(0, 1), (-1, 1), (-100, 1)])
    def test_below_minimum_clamps_to_min(self, value, expected):
        assert ToolCallBudgetPolicy.resolve(value) == expected

    @pytest.mark.parametrize("value", [21, 100, 10000])
    def test_above_maximum_clamps_to_max(self, value):
        assert ToolCallBudgetPolicy.resolve(value) == 20

    def test_bool_falls_back_to_default(self):
        """bool은 int의 하위형이지만 호출 상한 값으로는 무의미하다."""
        assert ToolCallBudgetPolicy.resolve(True) == 2
        assert ToolCallBudgetPolicy.resolve(False) == 2

    @pytest.mark.parametrize("value", ["3", 2.5, [], {}])
    def test_non_int_falls_back_to_default(self, value):
        """잘못된 저장값이 에이전트를 죽이지 않는다 — 기본값으로 낙하."""
        assert ToolCallBudgetPolicy.resolve(value) == 2

    def test_resolve_never_returns_zero(self):
        """0회면 도구를 아예 못 부른다 — 어떤 입력으로도 나오면 안 된다."""
        for value in (None, 0, -5, True, "x", 21):
            assert ToolCallBudgetPolicy.resolve(value) >= 1
