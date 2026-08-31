"""deep-search-pipeline Design §8.2 L1 — 종료 조건·예산 정책 (순수 도메인).

LLM·네트워크·LangGraph 없이 4중 종료 조건과 우선순위를 고정한다.
"""
import pytest

from src.domain.deep_search.policies import CoveragePolicy, DeepSearchBudgetPolicy
from src.domain.deep_search.schemas import Evidence, Requirement, SearchQuery, StopReason


def _reqs(*statuses: str) -> list[Requirement]:
    return [
        Requirement(id=f"r{i + 1}", description=f"요구 {i + 1}", status=s)
        for i, s in enumerate(statuses)
    ]


DEFAULT = DeepSearchBudgetPolicy()


# ── L1-1 ~ L1-6: 종료 조건 ──────────────────────────────────────


def test_l1_1_all_satisfied_returns_complete():
    """L1-1: 전 requirement 충족 → COMPLETE."""
    stop = CoveragePolicy.should_stop(
        requirements=_reqs("satisfied", "satisfied"),
        iteration=1,
        new_evidence_count=3,
        can_retry=True,
        budget=DEFAULT,
    )
    assert stop is StopReason.COMPLETE


def test_l1_2_max_iteration_reached():
    """L1-2: 반복 상한 도달 → MAX_ITERATION."""
    stop = CoveragePolicy.should_stop(
        requirements=_reqs("satisfied", "missing"),
        iteration=DEFAULT.max_iteration,
        new_evidence_count=2,
        can_retry=True,
        budget=DEFAULT,
    )
    assert stop is StopReason.MAX_ITERATION


def test_l1_3_cannot_retry_returns_exhausted():
    """L1-3: 재검색 전략 소진 → EXHAUSTED."""
    stop = CoveragePolicy.should_stop(
        requirements=_reqs("satisfied", "missing"),
        iteration=1,
        new_evidence_count=2,
        can_retry=False,
        budget=DEFAULT,
    )
    assert stop is StopReason.EXHAUSTED


def test_l1_4_no_information_gain_from_second_iteration():
    """L1-4: iteration>=2 이고 새 근거 0건 → NO_GAIN."""
    budget = DeepSearchBudgetPolicy(max_iteration=3)
    stop = CoveragePolicy.should_stop(
        requirements=_reqs("satisfied", "missing"),
        iteration=2,
        new_evidence_count=0,
        can_retry=True,
        budget=budget,
    )
    assert stop is StopReason.NO_GAIN


def test_l1_5_first_iteration_no_gain_does_not_stop():
    """L1-5 (D3): 1회차 무수확은 전략 전환 가치가 크므로 종료하지 않는다."""
    stop = CoveragePolicy.should_stop(
        requirements=_reqs("missing", "missing"),
        iteration=1,
        new_evidence_count=0,
        can_retry=True,
        budget=DEFAULT,
    )
    assert stop is None


def test_l1_6_complete_wins_over_max_iteration():
    """L1-6 (D4): 종료 조건 동시 성립 시 COMPLETE 우선."""
    stop = CoveragePolicy.should_stop(
        requirements=_reqs("satisfied", "satisfied"),
        iteration=DEFAULT.max_iteration,
        new_evidence_count=0,
        can_retry=False,
        budget=DEFAULT,
    )
    assert stop is StopReason.COMPLETE


def test_max_iteration_wins_over_exhausted_and_no_gain():
    """D4 우선순위: MAX_ITERATION > EXHAUSTED > NO_GAIN."""
    stop = CoveragePolicy.should_stop(
        requirements=_reqs("missing"),
        iteration=DEFAULT.max_iteration,
        new_evidence_count=0,
        can_retry=False,
        budget=DEFAULT,
    )
    assert stop is StopReason.MAX_ITERATION


def test_exhausted_wins_over_no_gain():
    """D4 우선순위: EXHAUSTED > NO_GAIN."""
    budget = DeepSearchBudgetPolicy(max_iteration=3)
    stop = CoveragePolicy.should_stop(
        requirements=_reqs("missing"),
        iteration=2,
        new_evidence_count=0,
        can_retry=False,
        budget=budget,
    )
    assert stop is StopReason.EXHAUSTED


def test_empty_requirements_is_complete_fail_open():
    """요구가 하나도 없으면 종료 (fail-open) — 무한 루프 방지."""
    stop = CoveragePolicy.should_stop(
        requirements=[],
        iteration=1,
        new_evidence_count=0,
        can_retry=True,
        budget=DEFAULT,
    )
    assert stop is StopReason.COMPLETE


def test_incomplete_within_budget_continues():
    """미충족 + 예산 여유 + 새 근거 있음 → 계속."""
    stop = CoveragePolicy.should_stop(
        requirements=_reqs("satisfied", "missing"),
        iteration=1,
        new_evidence_count=2,
        can_retry=True,
        budget=DEFAULT,
    )
    assert stop is None


# ── coverage 집계 ───────────────────────────────────────────────


def test_coverage_counts_satisfied():
    reqs = _reqs("satisfied", "missing", "satisfied")
    assert CoveragePolicy.satisfied_count(reqs) == 2
    assert CoveragePolicy.missing_ids(reqs) == ["r2"]


def test_missing_ids_empty_when_all_satisfied():
    assert CoveragePolicy.missing_ids(_reqs("satisfied")) == []


# ── 예산 정책 ───────────────────────────────────────────────────


def test_budget_defaults_match_design():
    """Design §2.2 비용 상한 계산의 전제값."""
    assert DEFAULT.max_iteration == 2
    assert DEFAULT.max_query_per_iteration == 5
    assert DEFAULT.max_result_per_query == 5
    assert DEFAULT.max_evidence_per_requirement == 8
    assert DEFAULT.min_confidence == pytest.approx(0.5)


def test_truncate_queries_reports_dropped_count():
    """E2: 예산 초과 쿼리는 절삭하고 개수를 반환한다 (암묵적 절삭 금지)."""
    queries = [SearchQuery(requirement_id=f"r{i}", query=f"q{i}") for i in range(8)]
    kept, dropped = DEFAULT.truncate_queries(queries)
    assert len(kept) == DEFAULT.max_query_per_iteration
    assert dropped == 3
    assert kept == queries[: DEFAULT.max_query_per_iteration]


def test_truncate_queries_no_drop_within_budget():
    queries = [SearchQuery(requirement_id="r1", query="q1")]
    kept, dropped = DEFAULT.truncate_queries(queries)
    assert kept == queries
    assert dropped == 0


# ── E7: Evidence 채택 규칙 ──────────────────────────────────────


def test_is_admissible_rejects_empty_source():
    """E7: 출처 없는 근거는 폐기 (환각 방지)."""
    ev = Evidence(requirement_id="r1", content="BIS 14.8%", source="", confidence=0.9)
    assert CoveragePolicy.is_admissible(ev, DEFAULT) is False


def test_is_admissible_rejects_low_confidence():
    ev = Evidence(
        requirement_id="r1", content="BIS 14.8%", source="http://x", confidence=0.2,
    )
    assert CoveragePolicy.is_admissible(ev, DEFAULT) is False


def test_is_admissible_rejects_empty_content():
    ev = Evidence(requirement_id="r1", content="   ", source="http://x", confidence=0.9)
    assert CoveragePolicy.is_admissible(ev, DEFAULT) is False


def test_is_admissible_accepts_valid_evidence():
    ev = Evidence(
        requirement_id="r1", content="BIS 14.8%", source="http://x", confidence=0.9,
    )
    assert CoveragePolicy.is_admissible(ev, DEFAULT) is True
