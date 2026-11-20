"""답변 인용 VO (answer-citation-verification §3.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CitationStatus = Literal["verified", "none"]
# none 사유: 모델이 인용을 안 달았음 / 모두 검증 탈락 / 판정기 실패
NoneReason = Literal["no_markers", "all_rejected", "judge_failed"]


@dataclass(frozen=True)
class RegisteredChunk:
    """번호 레지스트리 항목 — 답변 모델이 본 검색 청크."""

    marker: int
    chunk_id: str | None
    document_id: str | None
    page: int | None
    text: str


@dataclass(frozen=True)
class AnswerCitation:
    """저장·표시 단위 인용 1건 (답변 문장 × 청크)."""

    no: int  # 화면 번호(1부터 재번호, Design D-08)
    marker: int  # 레지스트리 번호(감사용)
    chunk_id: str | None
    document_id: str | None
    page: int | None
    evidence: str | None  # 청크에서 찾지 못하면 None (Design D-07)
    sentence: str  # 인용한 답변 문장(인용 표시 제외)


@dataclass(frozen=True)
class CitationOutcome:
    text: str  # 정리된 최종 본문
    status: CitationStatus
    citations: tuple[AnswerCitation, ...]
    none_reason: NoneReason | None = None
