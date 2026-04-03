"""PlanStep, PlanResult 도메인 스키마 테스트."""
import pytest
from pydantic import ValidationError

from src.domain.planner.schemas import PlanResult, PlanStep


class TestPlanStep:

    def test_frozen_immutable(self):
        step = PlanStep(step_index=0, description="검색", expected_output="문서 목록")
        with pytest.raises((AttributeError, TypeError, ValidationError)):
            step.step_index = 1  # type: ignore

    def test_tool_ids_default_empty(self):
        step = PlanStep(step_index=0, description="검색", expected_output="문서 목록")
        assert step.tool_ids == []

    def test_search_strategy_default_none(self):
        step = PlanStep(step_index=0, description="검색", expected_output="문서 목록")
        assert step.search_strategy is None

    def test_all_fields(self):
        step = PlanStep(
            step_index=2,
            description="하이브리드 검색",
            tool_ids=["search_tool"],
            search_strategy="hybrid",
            expected_output="관련 문서 5개",
        )
        assert step.step_index == 2
        assert step.description == "하이브리드 검색"
        assert step.tool_ids == ["search_tool"]
        assert step.search_strategy == "hybrid"
        assert step.expected_output == "관련 문서 5개"

    def test_step_index_must_be_non_negative(self):
        with pytest.raises(ValidationError):
            PlanStep(step_index=-1, description="검색", expected_output="결과")

    def test_description_must_not_be_empty(self):
        with pytest.raises(ValidationError):
            PlanStep(step_index=0, description="", expected_output="결과")

    def test_expected_output_must_not_be_empty(self):
        with pytest.raises(ValidationError):
            PlanStep(step_index=0, description="검색", expected_output="")


class TestPlanResult:

    def _make_step(self, index: int = 0) -> PlanStep:
        return PlanStep(
            step_index=index,
            description=f"단계 {index}",
            expected_output=f"출력 {index}",
        )

    def test_frozen_immutable(self):
        result = PlanResult(query="질문", confidence=0.9, reasoning="이유")
        with pytest.raises((AttributeError, TypeError, ValidationError)):
            result.query = "다른 질문"  # type: ignore

    def test_steps_default_empty(self):
        result = PlanResult(query="질문", confidence=0.9, reasoning="이유")
        assert result.steps == []

    def test_requires_clarification_default_false(self):
        result = PlanResult(query="질문", confidence=0.9, reasoning="이유")
        assert result.requires_clarification is False

    def test_clarifying_questions_default_empty(self):
        result = PlanResult(query="질문", confidence=0.9, reasoning="이유")
        assert result.clarifying_questions == []

    def test_all_fields(self):
        steps = [self._make_step(0), self._make_step(1)]
        result = PlanResult(
            query="복잡한 질문",
            steps=steps,
            confidence=0.85,
            reasoning="두 단계 필요",
            requires_clarification=False,
            clarifying_questions=[],
        )
        assert result.query == "복잡한 질문"
        assert len(result.steps) == 2
        assert result.confidence == 0.85
        assert result.reasoning == "두 단계 필요"

    def test_confidence_upper_bound(self):
        with pytest.raises(ValidationError):
            PlanResult(query="질문", confidence=1.1, reasoning="이유")

    def test_confidence_lower_bound(self):
        with pytest.raises(ValidationError):
            PlanResult(query="질문", confidence=-0.1, reasoning="이유")

    def test_query_must_not_be_empty(self):
        with pytest.raises(ValidationError):
            PlanResult(query="", confidence=0.9, reasoning="이유")

    def test_with_clarification(self):
        result = PlanResult(
            query="모호한 질문",
            confidence=0.5,
            reasoning="명확하지 않음",
            requires_clarification=True,
            clarifying_questions=["어떤 기간을 원하시나요?"],
        )
        assert result.requires_clarification is True
        assert len(result.clarifying_questions) == 1
