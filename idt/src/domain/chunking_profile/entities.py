"""ChunkingProfile 도메인 엔티티 (clause-aware-chunking Design §5.1).

조·항 경계 규칙(BoundaryRule)과 문서 유형별 기본 토큰/overlap을 함께 보유한다.
전역 기본값 = is_default=True 프로파일.
"""
from dataclasses import dataclass, field
from datetime import datetime

PARENT_LEVEL = "parent"
CHILD_LEVEL = "child"


@dataclass(frozen=True)
class BoundaryRule:
    """경계 규칙 하나 — 정규식 패턴 + 우선순위 + 계층(parent/child)."""

    pattern: str
    priority: int
    level: str  # "parent" | "child"


@dataclass
class ChunkingProfile:
    name: str
    boundary_rules: list[BoundaryRule] = field(default_factory=list)
    parent_chunk_size: int = 2000
    chunk_size: int = 500
    chunk_overlap: int = 50
    description: str | None = None
    is_default: bool = False
    # 섹션 요약 LLM(llm_model.id 소프트 참조). None=요약 비활성 (card-section-summary D2)
    summary_llm_model_id: str | None = None
    id: str | None = None  # UUID v4
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def parent_patterns(self) -> list[str]:
        """priority 오름차순으로 정렬된 parent 경계 패턴 목록."""
        return self._patterns_for(PARENT_LEVEL)

    def child_patterns(self) -> list[str]:
        """priority 오름차순으로 정렬된 child 경계 패턴 목록."""
        return self._patterns_for(CHILD_LEVEL)

    def _patterns_for(self, level: str) -> list[str]:
        rules = [r for r in self.boundary_rules if r.level == level]
        rules.sort(key=lambda r: r.priority)
        return [r.pattern for r in rules]
