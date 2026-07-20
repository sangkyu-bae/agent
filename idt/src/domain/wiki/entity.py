"""WikiArticle 도메인 엔티티.

LLM-WIKI-001: LLM Wiki(Self-Improving RAG) 정제 지식 항목.
외부 시스템(LLM/Qdrant/DB) 호출 없이 순수 값과 상태 전이만 보관한다.
검증 규칙은 src.domain.wiki.policies.WikiPolicy 가 담당한다(순환 참조 방지).
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class WikiSourceType(str, Enum):
    """위키 항목의 출처 유형."""

    DISTILLED = "distilled"        # 원본 문서 정제 (Phase 1, B)
    CONVERSATION = "conversation"  # 대화 환류 (Phase 3, A)
    WEBSEARCH = "websearch"        # 웹서치 환류 (Phase 3, A)
    HUMAN = "human"                # 사람 작성/편집 (C)


class WikiStatus(str, Enum):
    """위키 항목 라이프사이클 상태."""

    DRAFT = "draft"          # 자동 생성 초안 (검색 비노출)
    APPROVED = "approved"    # 승인됨 (검색 노출)
    DEPRECATED = "deprecated"  # 폐기/반려


@dataclass
class WikiArticle:
    """정제된 위키 지식 한 건.

    Attributes:
        id: PK
        agent_id: 소속 에이전트(Phase 1 스코프 키)
        title: 위키 항목 제목(검색 키)
        content: 정제 본문(문서/섹션 요약)
        source_type: 출처 유형
        source_refs: 출처 추적 식별자 목록(비면 생성 불가 — 출처 불변식)
        status: 라이프사이클 상태
        confidence: 신뢰도 0~1(환류 신호로 갱신)
        valid_until: 만료 시각(None이면 무기한, websearch는 설정 권장)
        version: 편집 버전
        editor_id: 마지막 편집자
        reviewer_id: 승인자
        created_at: 생성 시각
        updated_at: 최종 수정 시각
        path: 가상 폴더 경로("여신/한도"). None=미분류 (wiki-user-facing)
    """

    id: str
    agent_id: str
    title: str
    content: str
    source_type: WikiSourceType
    source_refs: list[str]
    status: WikiStatus = WikiStatus.DRAFT
    confidence: float = 0.5
    valid_until: datetime | None = None
    version: int = 1
    editor_id: str | None = None
    reviewer_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    path: str | None = None

    def mark_approved(self, reviewer_id: str, now: datetime) -> None:
        """승인 상태로 전이한다(전이 검증은 호출 측 정책이 선행)."""
        self.status = WikiStatus.APPROVED
        self.reviewer_id = reviewer_id
        self.updated_at = now

    def mark_deprecated(self, now: datetime) -> None:
        """폐기 상태로 전이한다."""
        self.status = WikiStatus.DEPRECATED
        self.updated_at = now

    def restore(self, now: datetime) -> None:
        """폐기 항목을 승인 상태로 복구한다."""
        self.status = WikiStatus.APPROVED
        self.updated_at = now

    def apply_edit(self, title: str, content: str, now: datetime) -> None:
        """본문/제목을 수정하고 버전을 올린다."""
        self.title = title
        self.content = content
        self.version += 1
        self.updated_at = now

    def is_expired(self, now: datetime) -> bool:
        """만료 시각이 지났는지 여부."""
        return self.valid_until is not None and self.valid_until <= now

    def is_searchable(self, now: datetime) -> bool:
        """검색에 노출 가능한지 여부(승인 + 미만료)."""
        return self.status == WikiStatus.APPROVED and not self.is_expired(now)
