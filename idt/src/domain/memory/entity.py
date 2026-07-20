"""Memory 도메인 엔티티 (agent-memory Phase 1).

사용자가 직접 등록한 배경 정보 한 건. General Chat 시스템 프롬프트에
상주 주입되는 Tier 0 메모리이며, Phase 2/3 확장 필드(scope/tier/status/
source_run_id/confidence)는 스키마 선반영만 하고 Phase 1에서는 고정값을 쓴다.
검증 규칙은 src.domain.memory.policies.MemoryPolicy 가 담당한다.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class MemoryScope(str, Enum):
    """메모리 소유 범위. Phase 1은 USER 고정, ORG는 Phase 3."""

    USER = "user"
    ORG = "org"


class MemoryType(str, Enum):
    """메모리 유형 — 주입 우선순위(MemoryPolicy.TYPE_PRIORITY)의 키."""

    PROFILE = "profile"          # 소속/역할 등 사용자 프로필
    PREFERENCE = "preference"    # 답변 형식 선호
    DOMAIN_TERM = "domain_term"  # 도메인 용어 정의
    EPISODE = "episode"          # 참고할 과거 맥락


class MemoryStatus(str, Enum):
    """라이프사이클 상태. Phase 1 수동 등록은 ACTIVE 고정."""

    PENDING = "pending"    # 자동 추출 후 승인 대기 (Phase 2)
    ACTIVE = "active"      # 주입 대상
    REJECTED = "rejected"  # 사용자가 거부 (Phase 2)
    EXPIRED = "expired"    # expires_at 경과 (Phase 2)


@dataclass
class Memory:
    """사용자 메모리 한 건.

    Attributes:
        id: PK (저장 전 None)
        scope: 소유 범위 (Phase 1은 USER)
        user_id: scope=USER일 때 소유자 (GeneralChatRequest.user_id와 동일 str 체계)
        tier: 0=상주 주입, 1=온디맨드(Phase 3)
        mem_type: 메모리 유형
        content: 본문 (MemoryPolicy.CONTENT_MAX 이하)
        source_run_id: 자동 추출 출처 run (Phase 2) — 수동 등록은 None
        confidence: 신뢰도 0~100 — 수동 입력은 100
        status: 라이프사이클 상태
        expires_at: 만료 시각 (Phase 2)
        created_at / updated_at: 저장소가 기록
    """

    id: int | None
    scope: MemoryScope
    user_id: str | None
    tier: int
    mem_type: MemoryType
    content: str
    source_run_id: str | None = None
    confidence: int = 100
    status: MemoryStatus = MemoryStatus.ACTIVE
    expires_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
