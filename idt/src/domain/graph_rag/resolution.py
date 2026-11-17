"""엔티티 동일성 판정 도메인 — 세 구간 정책·후보·판정 기록 VO.

Design Ref: graph-rag-foundation §2.2(판정)·§3.1·§3.3 V089, Plan FR-08~11.
- Jev ChoiceQuestion{C1..Ck, NEW} 의 후보 최대 확률 p* 로 구간을 나눈다:
  p* ≥ link → 연결, p* < new → 새 엔티티, 그 사이 → LLM 재판정(검토 대기).
- 타입이 다르면(둘 중 하나가 '기타'인 경우 제외) 후보에서 뺀다 — 다른 개념을
  이름만으로 합치지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from src.domain.graph_rag.value_objects import OTHER_TYPE

NEW_LABEL = "NEW"
MIN_VECTOR_SIMILARITY = 0.75


class ResolutionBand(StrEnum):
    AUTO_LINK = "auto_link"
    AUTO_NEW = "auto_new"
    REJUDGE = "rejudge"
    FALLBACK = "fallback"


class DecidedBy(StrEnum):
    RULE = "rule"
    JEV = "jev"
    LLM_REJUDGE = "llm_rejudge"
    LLM_FALLBACK = "llm_fallback"


class ReviewStatus(StrEnum):
    NONE = "none"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class LlmConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class Candidate:
    entity_id: str
    name: str
    type: str
    description: str
    aliases: tuple[str, ...]
    match: str  # "exact" | "alias" | "vector"
    similarity: float


@dataclass(frozen=True)
class ChooserVerdict:
    """판정자 응답 — Jev 는 probabilities, LLM 은 label·confidence·reason."""

    label: str
    probabilities: dict[str, float] | None = None
    confidence: LlmConfidence | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ResolutionDecision:
    """V089 graph_resolution_decision 한 행."""

    id: str
    job_id: str
    document_id: str
    chunk_id: str
    mention_text: str
    mention_type: str
    candidates: tuple[dict, ...]
    probabilities: dict[str, float] | None
    chosen_label: str
    entity_id: str
    created_new: bool
    decided_by: DecidedBy
    band: ResolutionBand
    probability: float | None
    llm_confidence: LlmConfidence | None = None
    llm_reason: str | None = None
    review_status: ReviewStatus = ReviewStatus.NONE
    reviewed_by: str | None = None
    reviewed_at: object = None
    review_note: str | None = None
    created_at: object = None
    extra: dict = field(default_factory=dict)


def types_compatible(a: str, b: str) -> bool:
    return a == b or OTHER_TYPE in (a, b)


def candidate_labels(candidates: list[Candidate]) -> dict[str, Candidate]:
    return {f"C{i}": c for i, c in enumerate(candidates, start=1)}


class ResolutionPolicy:
    @staticmethod
    def classify(
        p: float, *, link_threshold: float, new_threshold: float
    ) -> ResolutionBand:
        if p >= link_threshold:
            return ResolutionBand.AUTO_LINK
        if p < new_threshold:
            return ResolutionBand.AUTO_NEW
        return ResolutionBand.REJUDGE

    @staticmethod
    def best_candidate(probabilities: dict[str, float]) -> tuple[str, float]:
        """NEW 를 뺀 후보 중 최대 확률 — 후보가 없으면 (NEW, 0.0)."""
        scored = [(k, v) for k, v in probabilities.items() if k != NEW_LABEL]
        if not scored:
            return NEW_LABEL, 0.0
        return max(scored, key=lambda kv: kv[1])

    @staticmethod
    def unambiguous_exact(
        candidates: list[Candidate], mention_type: str
    ) -> Candidate | None:
        """정규화 이름·별칭 정확 일치이면서 같은 타입인 후보가 하나뿐이면 그 후보."""
        exact = [
            c
            for c in candidates
            if c.match in ("exact", "alias") and c.type == mention_type
        ]
        return exact[0] if len(exact) == 1 else None
