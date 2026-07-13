"""Routed Retrieval 도메인 VO (summary-routed-retrieval Design D1).

3계층 하강 파이프라인의 단계 간 계약. 외부 의존 없는 순수 값 객체 —
단계 구현 교체 시에도 이 계약은 불변이다.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RoutedScope:
    """검색 범위 — 컬렉션(None=기본) + 선택적 KB 격리."""

    collection_name: str | None = None
    kb_id: str | None = None


@dataclass(frozen=True)
class RoutedParams:
    """라우팅 파라미터 — 검증 규칙은 RoutedRetrievalPolicy (D13)."""

    doc_top_k: int = 5
    section_top_n: int = 10
    top_k: int = 5
    rrf_k: int = 60
    bm25_weight: float = 0.5
    vector_weight: float = 0.5


@dataclass(frozen=True)
class DocumentCandidate:
    """1차 라우팅 결과 — 문서 요약 근거 포함."""

    document_id: str
    score: float
    summary: str = ""
    keywords: list[str] = field(default_factory=list)
    filename: str = ""


@dataclass(frozen=True)
class SectionCandidate:
    """2차 라우팅 결과 — RRF 병합된 섹션 요약 근거 포함."""

    section_ref: str  # 원 parent chunk_id (rawchunk 확장 키)
    document_id: str
    score: float
    summary: str = ""
    clause_title: str = ""
    keywords: list[str] = field(default_factory=list)
    vector_rank: int | None = None
    bm25_rank: int | None = None
    source: str = "vector_only"  # "both" | "bm25_only" | "vector_only"


@dataclass(frozen=True)
class RoutedChunk:
    """3차 확장 결과 — 조(parent) 본문 + 라우팅 근거 (D7 응답 단위)."""

    section_ref: str
    document_id: str
    content: str
    score: float
    clause_title: str = ""
    document: DocumentCandidate | None = None
    section: SectionCandidate | None = None
    from_fallback: bool = False


@dataclass(frozen=True)
class RoutedRetrievalResult:
    """파이프라인 최종 결과 + 관측 필드 (D12)."""

    query: str
    results: list[RoutedChunk]
    fallback_used: bool
    fallback_count: int
    document_candidates: int
    section_candidates: int
    request_id: str
