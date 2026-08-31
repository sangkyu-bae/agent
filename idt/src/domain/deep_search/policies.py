"""deep-search-pipeline 도메인 정책 (Design §3, §6).

예산 상한과 4중 종료 조건을 LLM 없이 판정 가능한 순수 규칙으로 보관한다.
정책 값 변경은 이 파일의 상수만 수정한다 (config 하드코딩 금지 규칙).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from src.domain.deep_search.schemas import (
    MAX_EVIDENCE_PER_REQUIREMENT,
    Evidence,
    Requirement,
    SearchQuery,
    StopReason,
)


@dataclass(frozen=True)
class DeepSearchBudgetPolicy:
    """검색 예산 상한 (Plan FR-10 / Design §2.2).

    기본값은 NFR-02(LLM ≤12회, 검색 ≤10회)를 만족하도록 보수적으로 잡았다.
    테스트·후속 튜닝을 위해 인스턴스 단위 오버라이드를 허용한다.
    """

    MAX_SEARCH_ITERATION: ClassVar[int] = 2
    MAX_QUERY_PER_ITERATION: ClassVar[int] = 5
    MAX_RESULT_PER_QUERY: ClassVar[int] = 5
    MIN_CONFIDENCE: ClassVar[float] = 0.5
    EXTRACT_RESULT_HEAD: ClassVar[int] = 6000

    max_iteration: int = MAX_SEARCH_ITERATION
    max_query_per_iteration: int = MAX_QUERY_PER_ITERATION
    max_result_per_query: int = MAX_RESULT_PER_QUERY
    max_evidence_per_requirement: int = MAX_EVIDENCE_PER_REQUIREMENT
    min_confidence: float = MIN_CONFIDENCE
    extract_result_head: int = EXTRACT_RESULT_HEAD

    def truncate_queries(
        self, queries: list[SearchQuery],
    ) -> tuple[list[SearchQuery], int]:
        """예산 초과 쿼리를 절삭하고 (남긴 것, 버린 개수)를 반환 (E2).

        버린 개수를 함께 돌려주는 이유는 호출부가 반드시 로그를 남기게 하기
        위함이다 — 암묵적 절삭 금지 원칙.
        """
        limit = self.max_query_per_iteration
        if len(queries) <= limit:
            return list(queries), 0
        return list(queries[:limit]), len(queries) - limit


class CoveragePolicy:
    """커버리지 집계와 종료 판정 (Plan FR-09 / Design D3·D4)."""

    # D3: 1회차 무수확은 전략 전환 가치가 가장 큰 지점이므로 NO_GAIN을 적용하지 않는다.
    NO_GAIN_MIN_ITERATION: ClassVar[int] = 2

    SATISFIED: ClassVar[str] = "satisfied"
    MISSING: ClassVar[str] = "missing"

    @staticmethod
    def satisfied_count(requirements: list[Requirement]) -> int:
        return sum(1 for r in requirements if r.status == CoveragePolicy.SATISFIED)

    @staticmethod
    def missing_ids(requirements: list[Requirement]) -> list[str]:
        return [r.id for r in requirements if r.status != CoveragePolicy.SATISFIED]

    @classmethod
    def should_stop(
        cls,
        requirements: list[Requirement],
        iteration: int,
        new_evidence_count: int,
        can_retry: bool,
        budget: DeepSearchBudgetPolicy,
    ) -> StopReason | None:
        """종료 사유를 판정한다. 계속 진행해야 하면 None.

        우선순위 (D4): COMPLETE > MAX_ITERATION > EXHAUSTED > NO_GAIN.
        요구가 비어 있으면 COMPLETE로 본다 — fail-open(무한 루프 방지).
        """
        if not cls.missing_ids(requirements):
            return StopReason.COMPLETE
        if iteration >= budget.max_iteration:
            return StopReason.MAX_ITERATION
        if not can_retry:
            return StopReason.EXHAUSTED
        if iteration >= cls.NO_GAIN_MIN_ITERATION and new_evidence_count <= 0:
            return StopReason.NO_GAIN
        return None

    @staticmethod
    def is_admissible(evidence: Evidence, budget: DeepSearchBudgetPolicy) -> bool:
        """근거 채택 규칙 (E7) — 출처 없음·빈 내용·저신뢰는 폐기.

        환각 방지가 커버리지보다 우선한다 (D6).
        """
        if not evidence.source.strip() or not evidence.content.strip():
            return False
        return evidence.confidence >= budget.min_confidence
