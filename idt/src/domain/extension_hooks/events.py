"""코어 확장 지점 이벤트·요청 VO.

Design Ref: graph-rag-foundation §3.1 — 코어는 이 VO 와 ports.py 의 포트만 안다.
특정 확장(그래프 등)의 용어를 넣지 않는다.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from src.domain.hybrid_search.schemas import HybridSearchResult

_ADMIN_ROLE = "admin"


def _freeze(mapping: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(mapping or {}))


@dataclass(frozen=True)
class DocumentIngestedEvent:
    """KB 문서 업로드가 끝난 직후 (Qdrant·ES 쓰기 완료 뒤)."""

    document_id: str
    kb_id: str | None
    collection_name: str
    filename: str
    user_id: str
    chunk_count: int
    status: str  # "completed" | "partial" | "failed"


@dataclass(frozen=True)
class DocumentDeletedEvent:
    """문서 저장소(Qdrant·ES·메타데이터) 삭제가 끝난 직후."""

    document_id: str
    kb_id: str | None
    collection_name: str


@dataclass(frozen=True)
class SupplementalGrant:
    """실행별 "보조 검색 사용 허용" — 존재 자체가 대화 경로의 명시적 opt-in.

    Plan FR-20: 대화 라우트(WS·REST·SSE)만 만든다. 웹훅·백그라운드·스케줄·
    RAGAS·승인 재개는 만들지 않는다(None = 닫힘).
    """

    caller_is_admin: bool

    @classmethod
    def for_role(cls, role: str | None) -> SupplementalGrant:
        return cls(caller_is_admin=(role == _ADMIN_ROLE))


@dataclass(frozen=True)
class SupplementalQuery:
    """보조 검색 요청 — 도구가 이미 계산한 권한 필터를 그대로 넘긴다."""

    query: str
    top_k: int
    collection_name: str | None
    es_index: str | None
    hard_filter: Mapping[str, Any]
    lenient_filter: Mapping[str, Any]
    grant: SupplementalGrant
    request_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "hard_filter", _freeze(self.hard_filter))
        object.__setattr__(self, "lenient_filter", _freeze(self.lenient_filter))


@dataclass(frozen=True)
class SupplementalResult:
    """보조 검색 결과 — 빈 hits 와 skip_reason 으로 "실행 안 함"을 표현한다."""

    label: str
    hits: list[HybridSearchResult] = field(default_factory=list)
    weight: float = 0.5
    skip_reason: str | None = None
