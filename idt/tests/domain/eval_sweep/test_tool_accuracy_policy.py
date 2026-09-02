"""ToolAccuracyPolicy 단위 테스트.

Design Ref: §3.1 / D6 — expected_tools ∩ tools_used 집합 비교(순서 무시).
Design Ref: §3.5 / G6 — 측정 불가는 None(N/A), 0.0은 "측정했고 0점".
"""
import pytest

from src.domain.eval_sweep.policies import ToolAccuracyPolicy, mean_ignoring_none

KEYS = ("tool_precision", "tool_recall", "tool_f1")


class TestExpectedToolsMissing:
    """expected_tools 미기재 케이스는 집계에서 제외한다 (Plan FR-15)."""

    @pytest.mark.parametrize("expected", [None, []])
    def test_returns_all_none_not_zero(self, expected):
        scores = ToolAccuracyPolicy.score(expected, ["search_kb"])

        assert set(scores) == set(KEYS)
        # 0.0이 아니라 None이어야 한다 — 도구 미지원 모델의 부당한 0점 방지(Plan R-4)
        assert all(scores[k] is None for k in KEYS)


class TestSetComparison:
    def test_exact_match(self):
        scores = ToolAccuracyPolicy.score(["search_kb", "chart_builder"],
                                          ["search_kb", "chart_builder"])

        assert scores == {"tool_precision": 1.0, "tool_recall": 1.0, "tool_f1": 1.0}

    def test_order_is_ignored(self):
        """D6의 핵심 — 순서가 달라도 만점이어야 한다."""
        scores = ToolAccuracyPolicy.score(["search_kb", "chart_builder"],
                                          ["chart_builder", "search_kb"])

        assert scores["tool_f1"] == 1.0

    def test_duplicate_calls_collapse_to_set(self):
        """같은 도구를 두 번 불러도 집합이므로 1회로 취급한다."""
        scores = ToolAccuracyPolicy.score(["search_kb"],
                                          ["search_kb", "search_kb"])

        assert scores == {"tool_precision": 1.0, "tool_recall": 1.0, "tool_f1": 1.0}

    def test_missing_one_expected_tool(self):
        scores = ToolAccuracyPolicy.score(["search_kb", "chart_builder"], ["search_kb"])

        assert scores["tool_precision"] == 1.0
        assert scores["tool_recall"] == 0.5
        assert scores["tool_f1"] == pytest.approx(2 / 3)

    def test_extra_unexpected_tools_lower_precision(self):
        scores = ToolAccuracyPolicy.score(["search_kb"], ["search_kb", "web_search", "wiki_read"])

        assert scores["tool_precision"] == pytest.approx(1 / 3)
        assert scores["tool_recall"] == 1.0
        assert scores["tool_f1"] == pytest.approx(0.5)

    def test_no_tools_called_scores_zero_not_none(self):
        """기대는 있었는데 아무 도구도 안 불렀다 = 측정된 0점 (N/A 아님)."""
        scores = ToolAccuracyPolicy.score(["search_kb"], [])

        assert scores == {"tool_precision": 0.0, "tool_recall": 0.0, "tool_f1": 0.0}

    def test_completely_wrong_tools_score_zero(self):
        scores = ToolAccuracyPolicy.score(["search_kb"], ["web_search"])

        assert scores == {"tool_precision": 0.0, "tool_recall": 0.0, "tool_f1": 0.0}


class TestMeanIgnoringNone:
    """§3.5 규약 — N/A는 분모에서 제외한다."""

    def test_excludes_none_from_denominator(self):
        assert mean_ignoring_none([0.8, None, 0.6]) == pytest.approx(0.7)

    def test_zero_is_a_real_value(self):
        """0.0은 측정된 값이므로 평균에 반영된다."""
        assert mean_ignoring_none([1.0, 0.0]) == pytest.approx(0.5)

    @pytest.mark.parametrize("values", [[], [None, None]])
    def test_returns_none_when_no_valid_sample(self, values):
        assert mean_ignoring_none(values) is None
