"""AutoAgentBuilderPolicy: 자동 빌드 정책 상수 및 검증."""
from src.domain.auto_agent_builder.schemas import AgentSpecResult, AutoBuildSession


class AutoAgentBuilderPolicy:
    CONFIDENCE_THRESHOLD: float = 0.8
    MAX_ATTEMPTS: int = 3
    SESSION_TTL_SECONDS: int = 86400
    MAX_QUESTIONS_PER_TURN: int = 3

    @classmethod
    def is_confident_enough(cls, result: AgentSpecResult) -> bool:
        """확신도 ≥ 0.8 AND 추가 질문 없음."""
        return result.confidence >= cls.CONFIDENCE_THRESHOLD and not result.clarifying_questions

    @classmethod
    def should_force_create(cls, session: AutoBuildSession) -> bool:
        """최대 시도 횟수 도달 → best_effort 강제 생성."""
        return session.attempt_count >= cls.MAX_ATTEMPTS

    @classmethod
    def validate_tool_ids(cls, tool_ids: list[str], available_ids: set[str]) -> None:
        """tool_id가 tool_registry에 존재하는지 검증."""
        unknown = set(tool_ids) - available_ids
        if unknown:
            raise ValueError(f"Unknown tool_ids from LLM response: {unknown}")
