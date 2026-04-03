"""PlannerPolicy 도메인 정책 테스트."""
import pytest

from src.domain.planner.policies import PlannerPolicy
from src.domain.planner.schemas import PlanResult, PlanStep


def _make_step() -> PlanStep:
    return PlanStep(step_index=0, description="검색", expected_output="문서")


def _make_result(
    confidence: float = 0.9,
    steps: list | None = None,
    requires_clarification: bool = False,
) -> PlanResult:
    return PlanResult(
        query="질문",
        steps=steps if steps is not None else [_make_step()],
        confidence=confidence,
        reasoning="이유",
        requires_clarification=requires_clarification,
    )


class TestPlannerPolicy:

    def test_is_plan_acceptable_true(self):
        result = _make_result(confidence=0.9)
        assert PlannerPolicy.is_plan_acceptable(result) is True

    def test_is_plan_acceptable_at_threshold(self):
        result = _make_result(confidence=0.75)
        assert PlannerPolicy.is_plan_acceptable(result) is True

    def test_is_plan_acceptable_false_low_confidence(self):
        result = _make_result(confidence=0.74)
        assert PlannerPolicy.is_plan_acceptable(result) is False

    def test_is_plan_acceptable_false_empty_steps(self):
        result = _make_result(confidence=0.9, steps=[])
        assert PlannerPolicy.is_plan_acceptable(result) is False

    def test_is_plan_acceptable_false_requires_clarification(self):
        result = _make_result(confidence=0.9, requires_clarification=True)
        assert PlannerPolicy.is_plan_acceptable(result) is False

    def test_needs_replan_mirrors_is_plan_acceptable(self):
        acceptable = _make_result(confidence=0.9)
        unacceptable = _make_result(confidence=0.5)
        assert PlannerPolicy.needs_replan(acceptable) is False
        assert PlannerPolicy.needs_replan(unacceptable) is True

    def test_is_max_attempts_reached_false(self):
        assert PlannerPolicy.is_max_attempts_reached(1) is False

    def test_is_max_attempts_reached_at_limit(self):
        assert PlannerPolicy.is_max_attempts_reached(PlannerPolicy.MAX_REPLAN_ATTEMPTS) is True

    def test_is_max_attempts_reached_over_limit(self):
        assert PlannerPolicy.is_max_attempts_reached(PlannerPolicy.MAX_REPLAN_ATTEMPTS + 1) is True

    def test_constants(self):
        assert PlannerPolicy.CONFIDENCE_THRESHOLD == 0.75
        assert PlannerPolicy.MAX_STEPS == 10
        assert PlannerPolicy.MAX_REPLAN_ATTEMPTS == 2
