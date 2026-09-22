"""builtin-middleware D1: 미들웨어 도메인 엔티티/VO.

v2 실험 경로(domain/middleware_agent)와 독립 — 카탈로그(관리자 제어) 소유 모델.
langchain 클래스 참조 금지(도메인 순수성) — 인스턴스화는 application의
MiddlewareBuilder가 전담한다.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class MiddlewareType(str, Enum):
    """1차 빌트인 미들웨어 4종 (실행 안정성 축) + 승인 게이트.

    approval-gate Design §3.3: APPROVAL_GATE 는 안정성이 아니라 **안전** 축이라
    조립 실패 시 정책이 다르다 — 나머지는 warning 후 스킵이지만 게이트는
    예외를 재전파한다(fail-closed). MiddlewareBuilder.build 참조.
    """

    MODEL_RETRY = "model_retry"
    TOOL_RETRY = "tool_retry"
    MODEL_FALLBACK = "model_fallback"
    MODEL_CALL_LIMIT = "model_call_limit"
    APPROVAL_GATE = "approval_gate"


# approval-gate Check G3: 전용 API 가 소유하는 미들웨어 타입.
# 에이전트 폼 저장(_sync_middleware, 전체 교체)은 이 타입의 행을 삭제·재삽입하지
# 않는다. 그렇지 않으면 전용 API 로 저장한 설정(execute_after 등)이 에이전트를
# 한 번 수정할 때마다 폼 목록에 없다는 이유로 지워진다.
SEPARATELY_MANAGED_MIDDLEWARE_TYPES: frozenset[str] = frozenset(
    {MiddlewareType.APPROVAL_GATE.value}
)


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
    """실행 조립용 VO — 스냅샷 ∪ enforced 병합 결과.

    approval-gate Design §3.4: config 는 `카탈로그 default_config ∪ 에이전트
    record.config`(record 우선) 다. 기존 4종은 record.config 가 비어 있어
    default_config 그대로 — 무회귀.

    `is_enforced` 를 싣는 이유: 승인 게이트가 런타임에 `mode="off"` 를
    이겨야 하는데, 그 판정을 하려면 강제 여부를 알아야 한다. 기본값 False 라
    기존 생성부는 수정이 필요 없다 (additive).
    """

    middleware_type: MiddlewareType
    config: dict
    sort_order: int
    is_enforced: bool = False
