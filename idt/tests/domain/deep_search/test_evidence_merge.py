"""deep-search-pipeline Design §8.2 L1-7/L1-8 — EvidenceStore(reducer) 규칙.

merge_evidence는 LangGraph state reducer로 쓰이지만 순수 함수이므로
langgraph 없이 단독 검증한다 (D5).
"""
from src.domain.deep_search.schemas import (
    MAX_EVIDENCE_PER_REQUIREMENT,
    Evidence,
    Requirement,
    SearchQuery,
    StopReason,
    count_new_evidence,
    merge_evidence,
)


def _ev(req: str, content: str, source: str = "http://a", conf: float = 0.8) -> Evidence:
    return Evidence(
        requirement_id=req, content=content, source=source, confidence=conf,
    )


# ── L1-7: 중복 제거 ─────────────────────────────────────────────


def test_l1_7_identical_evidence_is_deduped():
    """동일 (requirement_id, source, content) 는 1건으로 병합."""
    existing = [_ev("r1", "BIS 14.8%")]
    new = [_ev("r1", "BIS 14.8%")]
    merged = merge_evidence(existing, new)
    assert len(merged) == 1


def test_l1_7_duplicate_keeps_higher_confidence():
    existing = [_ev("r1", "BIS 14.8%", conf=0.6)]
    new = [_ev("r1", "BIS 14.8%", conf=0.95)]
    merged = merge_evidence(existing, new)
    assert len(merged) == 1
    assert merged[0].confidence == 0.95


def test_l1_7_different_source_is_not_duplicate():
    existing = [_ev("r1", "BIS 14.8%", source="http://a")]
    new = [_ev("r1", "BIS 14.8%", source="http://b")]
    assert len(merge_evidence(existing, new)) == 2


def test_l1_7_different_requirement_is_not_duplicate():
    existing = [_ev("r1", "BIS 14.8%")]
    new = [_ev("r2", "BIS 14.8%")]
    assert len(merge_evidence(existing, new)) == 2


def test_l1_7_dedup_uses_content_prefix():
    """content 앞 120자가 같으면 동일 근거로 본다 (렌더 길이 편차 흡수)."""
    head = "가" * 120
    existing = [_ev("r1", head + "꼬리A")]
    new = [_ev("r1", head + "꼬리B")]
    assert len(merge_evidence(existing, new)) == 1


def test_merge_preserves_existing_order_then_appends():
    existing = [_ev("r1", "A"), _ev("r1", "B")]
    new = [_ev("r1", "C")]
    merged = merge_evidence(existing, new)
    assert [e.content for e in merged] == ["A", "B", "C"]


def test_merge_into_empty_store():
    new = [_ev("r1", "A")]
    assert merge_evidence([], new) == new


def test_merge_with_empty_new_is_noop():
    existing = [_ev("r1", "A")]
    assert merge_evidence(existing, []) == existing


# ── L1-8: requirement별 상한 ────────────────────────────────────


def test_l1_8_caps_per_requirement():
    """requirement당 상한 초과 시 상한 길이로 절삭."""
    new = [_ev("r1", f"근거{i}", conf=0.9) for i in range(MAX_EVIDENCE_PER_REQUIREMENT + 4)]
    merged = merge_evidence([], new)
    assert len(merged) == MAX_EVIDENCE_PER_REQUIREMENT


def test_l1_8_drops_lowest_confidence_first():
    """절삭은 confidence 낮은 순."""
    high = [_ev("r1", f"높음{i}", conf=0.9) for i in range(MAX_EVIDENCE_PER_REQUIREMENT)]
    low = [_ev("r1", "낮음", conf=0.1)]
    merged = merge_evidence(high, low)
    assert len(merged) == MAX_EVIDENCE_PER_REQUIREMENT
    assert all(e.content != "낮음" for e in merged)


def test_l1_8_cap_is_applied_per_requirement_independently():
    r1 = [_ev("r1", f"a{i}") for i in range(MAX_EVIDENCE_PER_REQUIREMENT + 2)]
    r2 = [_ev("r2", "b0")]
    merged = merge_evidence([], r1 + r2)
    assert len([e for e in merged if e.requirement_id == "r1"]) == MAX_EVIDENCE_PER_REQUIREMENT
    assert len([e for e in merged if e.requirement_id == "r2"]) == 1


# ── new_evidence_count (NO_GAIN 판정 입력) ──────────────────────


def test_count_new_evidence_ignores_duplicates():
    """NO_GAIN 판정은 '실제로 새로 들어온 근거 수'를 세야 한다."""
    existing = [_ev("r1", "A")]
    incoming = [_ev("r1", "A"), _ev("r1", "B")]
    assert count_new_evidence(existing, incoming) == 1


def test_count_new_evidence_all_duplicates_is_zero():
    existing = [_ev("r1", "A")]
    assert count_new_evidence(existing, [_ev("r1", "A")]) == 0


def test_count_new_evidence_on_empty_store():
    assert count_new_evidence([], [_ev("r1", "A"), _ev("r2", "B")]) == 2


# ── 스키마 기본값 ───────────────────────────────────────────────


def test_requirement_defaults_to_missing():
    req = Requirement(id="r1", description="요구")
    assert req.status == "missing"
    assert req.constraints == {}


def test_requirement_constraints_are_free_form():
    """AD-5: entity/metric/period는 고정 필드가 아니라 constraints의 선택 키."""
    req = Requirement(
        id="r1",
        description="상상인플러스저축은행의 BIS 자기자본비율",
        constraints={"entity": "상상인플러스저축은행", "period": "latest"},
    )
    assert req.constraints["period"] == "latest"

    plain = Requirement(id="r2", description="쿠버네티스 Service의 정의")
    assert plain.constraints == {}


def test_evidence_attrs_default_empty():
    ev = _ev("r1", "A")
    assert ev.attrs == {}


def test_search_query_binds_to_requirement():
    q = SearchQuery(requirement_id="r1", query="상상인플러스저축은행 BIS 비율")
    assert q.requirement_id == "r1"


def test_stop_reason_values():
    assert StopReason.COMPLETE.value == "complete"
    assert StopReason.MAX_ITERATION.value == "max_iteration"
    assert StopReason.NO_GAIN.value == "no_gain"
    assert StopReason.EXHAUSTED.value == "exhausted"
    assert StopReason.FALLBACK.value == "fallback"
