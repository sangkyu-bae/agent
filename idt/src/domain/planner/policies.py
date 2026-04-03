"""PlannerPolicy: 계획 품질 판정 정책."""
from src.domain.planner.schemas import PlanResult


class PlannerPolicy:
    CONFIDENCE_THRESHOLD: float = 0.75
    MAX_STEPS: int = 10
    MAX_REPLAN_ATTEMPTS: int = 2

    @classmethod
    def is_plan_acceptable(cls, result: PlanResult) -> bool:
        """계획이 실행 가능한 품질인지 판정."""
        return (
            result.confidence >= cls.CONFIDENCE_THRESHOLD
            and len(result.steps) > 0
            and not result.requires_clarification
        )

    @classmethod
    def needs_replan(cls, result: PlanResult) -> bool:
        """재계획이 필요한지 판정."""
        return not cls.is_plan_acceptable(result)

    @classmethod
    def is_max_attempts_reached(cls, attempt_count: int) -> bool:
        return attempt_count >= cls.MAX_REPLAN_ATTEMPTS
