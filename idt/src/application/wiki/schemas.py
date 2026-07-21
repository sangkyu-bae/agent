"""Application DTO: 위키 정제 입출력 스키마 (LLM-WIKI-001)."""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class WikiSourceGroup:
    """정제 대상 원본 청크 묶음(주제/섹션 단위).

    Attributes:
        topic_hint: 주제 힌트(제목 생성 참고용, 없을 수 있음)
        texts: 원본 청크 본문 목록
        refs: 출처 추적 식별자(비면 정제 항목이 생성되지 않음 — 출처 불변식)
    """

    topic_hint: str | None
    texts: list[str]
    refs: list[str] = field(default_factory=list)


@dataclass
class DistilledContent:
    """LLM 정제 결과(제목 + 본문)."""

    title: str
    content: str


@dataclass
class FeedbackWikiDraft:
    """부정 평가 환류 초안 (wiki-feedback-loop §3-2).

    confidence는 LLM 판정 점수(0~100)를 /100 클램프한 값.
    match_id: 같은 주제로 판정된 기존 draft id (recurring-feedback-promotion).
    None이면 신규 draft 생성.
    """

    title: str
    content: str
    confidence: float
    match_id: str | None = None


@dataclass
class WikiTreeItem:
    """지식 트리 항목 — 본문 제외 경량 조회 (wiki-user-facing)."""

    id: str
    title: str
    status: str
    source_type: str
    path: str | None
    updated_at: datetime | None = None
