"""엔티티 판정 도메인 — 세 구간·타입 호환·Jev 라벨 (Design §2.2 판정, Plan FR-08~10)."""
import pytest
from src.domain.graph_rag.resolution import (
    NEW_LABEL,
    Candidate,
    ResolutionBand,
    ResolutionPolicy,
    candidate_labels,
    types_compatible,
)


@pytest.mark.parametrize("p, band", [
    (0.95, ResolutionBand.AUTO_LINK), (0.8, ResolutionBand.AUTO_LINK),
    (0.79, ResolutionBand.REJUDGE), (0.4, ResolutionBand.REJUDGE),
    (0.39, ResolutionBand.AUTO_NEW), (0.0, ResolutionBand.AUTO_NEW),
])
def test_classify_bands(p, band):
    assert ResolutionPolicy.classify(p, link_threshold=0.8, new_threshold=0.4) is band


def test_best_candidate_ignores_new_label():
    probs = {"C1": 0.2, "C2": 0.5, NEW_LABEL: 0.3}
    assert ResolutionPolicy.best_candidate(probs) == ("C2", 0.5)
    assert ResolutionPolicy.best_candidate({NEW_LABEL: 1.0}) == (NEW_LABEL, 0.0)


@pytest.mark.parametrize("a, b, ok", [
    ("상품", "상품", True), ("상품", "기타", True), ("기타", "대상", True),
    ("상품", "대상", False),
])
def test_types_compatible(a, b, ok):
    assert types_compatible(a, b) is ok


def test_candidate_labels_are_stable():
    cands = [
        Candidate("e1", "A상품", "상품", "", (), "exact", 1.0),
        Candidate("e2", "에이상품", "상품", "", ("A 상품",), "vector", 0.81),
    ]
    labels = candidate_labels(cands)
    assert list(labels) == ["C1", "C2"]
    assert labels["C2"].entity_id == "e2"


def test_single_exact_same_type_is_unambiguous():
    exact = Candidate("e1", "A상품", "상품", "", (), "exact", 1.0)
    vec = Candidate("e2", "B상품", "상품", "", (), "vector", 0.8)
    assert ResolutionPolicy.unambiguous_exact([exact], "상품") is exact
    assert ResolutionPolicy.unambiguous_exact([exact, vec], "상품") is exact
    other = Candidate("e3", "A상품", "상품", "", (), "exact", 1.0)
    assert ResolutionPolicy.unambiguous_exact([exact, other], "상품") is None
    assert ResolutionPolicy.unambiguous_exact([vec], "상품") is None
