"""PlannerPolicy 단위 테스트 — HITL 질문 판정 도메인 규칙 (fix-agent-planner-hitl)."""
from src.domain.agent_composer.policies import PlannerPolicy
from src.domain.agent_composer.schemas import ClarifyingQuestion


def _question(i: int) -> ClarifyingQuestion:
    return ClarifyingQuestion(
        id=f"q{i}",
        question=f"질문 {i}?",
        options=["선택지 A", "선택지 B"],
    )


class TestShouldAsk:
    def test_low_confidence_with_questions_asks(self):
        assert PlannerPolicy.should_ask(0.5, question_count=2, round_=0) is True

    def test_confidence_at_threshold_does_not_ask(self):
        assert PlannerPolicy.should_ask(0.8, question_count=2, round_=0) is False

    def test_no_questions_does_not_ask(self):
        assert PlannerPolicy.should_ask(0.3, question_count=0, round_=0) is False

    def test_round_exhausted_forces_proceed(self):
        """FR-04: 라운드 상한 도달 시 질문이 있어도 강제 진행."""
        assert (
            PlannerPolicy.should_ask(
                0.3, question_count=3, round_=PlannerPolicy.MAX_CLARIFICATION_ROUNDS
            )
            is False
        )

    def test_last_allowed_round_still_asks(self):
        assert (
            PlannerPolicy.should_ask(
                0.3,
                question_count=1,
                round_=PlannerPolicy.MAX_CLARIFICATION_ROUNDS - 1,
            )
            is True
        )


class TestClampRound:
    def test_negative_clamped_to_zero(self):
        assert PlannerPolicy.clamp_round(-3) == 0

    def test_oversized_clamped_to_max(self):
        assert (
            PlannerPolicy.clamp_round(99)
            == PlannerPolicy.MAX_CLARIFICATION_ROUNDS
        )

    def test_in_range_passes_through(self):
        assert PlannerPolicy.clamp_round(1) == 1


class TestClampQuestions:
    def test_over_limit_truncated(self):
        questions = [_question(i) for i in range(5)]
        clamped = PlannerPolicy.clamp_questions(questions)
        assert len(clamped) == PlannerPolicy.MAX_QUESTIONS_PER_ROUND
        assert clamped[0].id == "q0"

    def test_under_limit_passes_through(self):
        questions = [_question(0)]
        assert PlannerPolicy.clamp_questions(questions) == questions

    def test_empty_stays_empty(self):
        assert PlannerPolicy.clamp_questions([]) == []
