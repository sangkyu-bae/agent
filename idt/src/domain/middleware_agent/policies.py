"""MiddlewareAgentPolicy: 에이전트 + 미들웨어 조합 유효성 검사."""
from src.domain.middleware_agent.schemas import MiddlewareConfig


class MiddlewareAgentPolicy:
    MIN_TOOLS: int = 1
    MAX_TOOLS: int = 5
    MAX_MIDDLEWARE: int = 5
    MAX_SYSTEM_PROMPT_LEN: int = 4000

    @classmethod
    def validate_tool_count(cls, tool_ids: list[str]) -> None:
        """1 ≤ 도구 수 ≤ 5."""
        count = len(tool_ids)
        if not (cls.MIN_TOOLS <= count <= cls.MAX_TOOLS):
            raise ValueError(
                f"tool_ids must have {cls.MIN_TOOLS}~{cls.MAX_TOOLS} items, got {count}"
            )

    @classmethod
    def validate_middleware_count(cls, middlewares: list[MiddlewareConfig]) -> None:
        """0 ≤ 미들웨어 수 ≤ 5."""
        if len(middlewares) > cls.MAX_MIDDLEWARE:
            raise ValueError(
                f"middleware count must be ≤ {cls.MAX_MIDDLEWARE}, got {len(middlewares)}"
            )

    @classmethod
    def validate_middleware_combination(cls, middlewares: list[MiddlewareConfig]) -> None:
        """동일 MiddlewareType 중복 금지."""
        types = [m.middleware_type for m in middlewares]
        if len(types) != len(set(types)):
            raise ValueError("Duplicate middleware types are not allowed")

    @classmethod
    def validate_system_prompt(cls, prompt: str) -> None:
        """시스템 프롬프트 길이 ≤ 4000자."""
        if len(prompt) > cls.MAX_SYSTEM_PROMPT_LEN:
            raise ValueError(
                f"system_prompt must be ≤ {cls.MAX_SYSTEM_PROMPT_LEN} chars, got {len(prompt)}"
            )
