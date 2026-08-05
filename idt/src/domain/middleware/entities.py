"""builtin-middleware D1: 미들웨어 도메인 엔티티/VO.

v2 실험 경로(domain/middleware_agent)와 독립 — 카탈로그(관리자 제어) 소유 모델.
langchain 클래스 참조 금지(도메인 순수성) — 인스턴스화는 application의
MiddlewareBuilder가 전담한다.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MiddlewareType(str, Enum):
    """1차 빌트인 미들웨어 4종 (실행 안정성 축)."""

    MODEL_RETRY = "model_retry"
    TOOL_RETRY = "tool_retry"
    MODEL_FALLBACK = "model_fallback"
    MODEL_CALL_LIMIT = "model_call_limit"


@dataclass
class MiddlewareCatalogEntry:
    """미들웨어 카탈로그 행 — 빌트인/강제 플래그와 기본 설정의 런타임 SoT."""

    id: str
    middleware_type: MiddlewareType
    name: str
    description: str
    is_builtin: bool = False
    is_enforced: bool = False
    default_config: dict = field(default_factory=dict)
    is_active: bool = True
    sort_order: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class AgentMiddlewareRecord:
    """에이전트별 적용 스냅샷 행 (행 존재 = 적용, config는 후속 오버라이드 예약)."""

    agent_id: str
    middleware_type: str
    sort_order: int = 0
    config: dict | None = None


@dataclass(frozen=True)
class AppliedMiddleware:
    """실행 조립용 VO — 스냅샷 ∪ enforced 병합 결과 (config는 카탈로그 해석)."""

    middleware_type: MiddlewareType
    config: dict
    sort_order: int
