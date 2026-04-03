"""도메인 스키마: MiddlewareType, MiddlewareConfig, MiddlewareAgentDefinition."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MiddlewareType(str, Enum):
    SUMMARIZATION = "summarization"
    PII = "pii"
    TOOL_RETRY = "tool_retry"
    MODEL_CALL_LIMIT = "model_call_limit"
    MODEL_FALLBACK = "model_fallback"


@dataclass(frozen=True)
class MiddlewareConfig:
    """단일 미들웨어 설정 Value Object."""

    middleware_type: MiddlewareType
    config: dict
    sort_order: int = 0


@dataclass
class MiddlewareAgentDefinition:
    """에이전트 + 미들웨어 구성 도메인 객체."""

    id: str
    user_id: str
    name: str
    description: str
    system_prompt: str
    model_name: str
    tool_ids: list[str]
    middleware_configs: list[MiddlewareConfig]
    status: str
    created_at: datetime
    updated_at: datetime

    def sorted_middleware(self) -> list[MiddlewareConfig]:
        """sort_order 기준 정렬된 미들웨어 목록 반환."""
        return sorted(self.middleware_configs, key=lambda m: m.sort_order)

    def apply_update(
        self,
        system_prompt: str | None,
        name: str | None,
        middleware_configs: list[MiddlewareConfig] | None,
    ) -> None:
        """업데이트 적용."""
        if system_prompt is not None:
            self.system_prompt = system_prompt
        if name is not None:
            self.name = name
        if middleware_configs is not None:
            self.middleware_configs = middleware_configs
