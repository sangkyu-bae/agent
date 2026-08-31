"""deep-search-pipeline 도메인 스키마 (Design §3).

Requirement / Evidence / SearchQuery 는 검색 파이프라인의 상태 단위이며,
`merge_evidence`는 LangGraph state reducer로 쓰이지만 **순수 함수**다 (D5).
이 모듈은 외부 라이브러리를 import하지 않는다 (§9.2).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Annotated, TypedDict

# ── 상수 ─────────────────────────────────────────────────────────

# requirement 하나가 보유할 수 있는 최대 근거 수. 초과분은 confidence 낮은 순 절삭.
MAX_EVIDENCE_PER_REQUIREMENT = 8

# 중복 판정에 사용할 content 접두 길이 — 렌더 길이 편차를 흡수한다.
DEDUP_CONTENT_PREFIX = 120


class StopReason(str, Enum):
    """루프 종료 사유 (Design §3.1) — 로그·요약 문자열의 단일 출처."""

    COMPLETE = "complete"            # 모든 requirement 충족
    MAX_ITERATION = "max_iteration"  # 반복 상한 도달
    NO_GAIN = "no_gain"              # 새 근거 0건
    EXHAUSTED = "exhausted"          # 재검색 전략 소진 (검색 전량 실패 포함)
    EVAL_FAILED = "eval_failed"      # 충족 판정 불가 → fail-open 종료 (D7)
    FALLBACK = "fallback"            # 서브그래프 예외 → legacy 단일 쿼리 경로 (E10)


# ── 엔티티 ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class Requirement:
    """질문이 요구하는 정보 단위 하나 (fact slot).

    AD-5: entity/metric/period 같은 도메인 어휘는 고정 필드가 아니라
    `constraints`의 선택 키다. 코어는 이 키를 이름으로 분기하지 않는다.
    """

    id: str
    description: str
    constraints: dict[str, str] = field(default_factory=dict)
    status: str = "missing"  # missing | satisfied


@dataclass(frozen=True)
class SearchQuery:
    """requirement 하나를 겨냥한 검색 쿼리."""

    requirement_id: str
    query: str


@dataclass(frozen=True)
class Evidence:
    """검색 결과에서 추출한 구조화 근거.

    `source`는 필수다 — 비어 있으면 CoveragePolicy.is_admissible이 폐기한다 (E7).
    """

    requirement_id: str
    content: str
    source: str
    confidence: float = 0.0
    attrs: dict[str, str] = field(default_factory=dict)


# ── EvidenceStore (reducer) ──────────────────────────────────────


def _dedup_key(evidence: Evidence) -> tuple[str, str, str]:
    return (
        evidence.requirement_id,
        evidence.source,
        evidence.content[:DEDUP_CONTENT_PREFIX],
    )


def _apply_cap(items: list[Evidence], cap: int) -> list[Evidence]:
    """requirement별 상한 초과분을 confidence 낮은 순으로 절삭."""
    by_requirement: dict[str, list[int]] = defaultdict(list)
    for index, evidence in enumerate(items):
        by_requirement[evidence.requirement_id].append(index)

    dropped: set[int] = set()
    for indices in by_requirement.values():
        if len(indices) <= cap:
            continue
        ranked = sorted(indices, key=lambda i: items[i].confidence, reverse=True)
        dropped.update(ranked[cap:])

    if not dropped:
        return items
    return [ev for index, ev in enumerate(items) if index not in dropped]


def merge_evidence(
    existing: list[Evidence], new: list[Evidence],
) -> list[Evidence]:
    """LangGraph state reducer — EvidenceStore 역할 (D5).

    - 중복(requirement_id, source, content 접두)은 1건으로 병합하며 confidence가
      높은 쪽을 남긴다.
    - 기존 항목의 순서를 보존하고 신규 항목을 뒤에 잇는다.
    - requirement별 MAX_EVIDENCE_PER_REQUIREMENT를 초과하면 confidence 낮은 순 절삭.

    LangGraph 리듀서 계약상 시그니처는 반드시 (a, b) -> c 두 개여야 한다.
    """
    if not new:
        return list(existing)

    merged: dict[tuple[str, str, str], Evidence] = {}
    for evidence in [*existing, *new]:
        key = _dedup_key(evidence)
        previous = merged.get(key)
        if previous is None or evidence.confidence > previous.confidence:
            merged[key] = evidence

    return _apply_cap(list(merged.values()), MAX_EVIDENCE_PER_REQUIREMENT)


def count_new_evidence(existing: list[Evidence], incoming: list[Evidence]) -> int:
    """실제로 새로 확보된 근거 수 — NO_GAIN 판정 입력 (Design §3.2)."""
    known = {_dedup_key(ev) for ev in existing}
    return len({_dedup_key(ev) for ev in incoming} - known)


# ── 워크플로우 State ─────────────────────────────────────────────


class DeepSearchState(TypedDict):
    """서브그래프 State (Design §3.2).

    `evidence`의 Annotated 리듀서는 stdlib typing만 사용하므로 이 모듈에
    langgraph 의존이 생기지 않는다.
    """

    question: str
    context: str
    user_context: str
    strategy: str  # single | parallel | iterative
    requirements: list[Requirement]
    pending_queries: list[SearchQuery]
    query_history: list[str]
    raw_results: list[tuple[str, bool, str]]  # (query, ok, text)
    evidence: Annotated[list[Evidence], merge_evidence]
    iteration: int
    new_evidence_count: int
    can_retry: bool
    stop_reason: str
    search_ok: bool
    extract_degraded: bool
    plan_fallback: bool
    llm_chars: int
    body: str      # finalize 산출 — 워커 메시지 본문
    summary: str   # finalize 산출 — step output 요약
