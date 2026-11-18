"""그래프 검색 도메인 정책 (Design §2.2 검색, module-5)."""

import pytest

from src.domain.graph_rag.retrieval import (
    MAX_GRAPH_CHUNKS,
    PathHit,
    RetrievalPolicy,
)


def test_phrases_are_noun_ngrams_with_and_without_space():
    phrases = RetrievalPolicy.phrases(["운전", "자금", "대출", "한도"])
    assert "운전자금대출" in phrases and "운전 자금 대출" in phrases
    assert "대출 한도" in phrases and "한도" in phrases
    assert all(len(p.split()) <= 3 for p in phrases)  # 최대 3개 묶음


def test_phrases_drop_one_char_singletons_and_duplicates():
    phrases = RetrievalPolicy.phrases(["A", "상품", "상품", "대상"])
    assert "a" not in phrases
    assert phrases.count("상품") == 1
    assert "a상품" in phrases  # 한 글자도 묶음 안에서는 쓴다


def test_hop_bound_is_validated():
    assert RetrievalPolicy.hops(2) == 2
    for bad in (0, 4, -1):
        with pytest.raises(ValueError):
            RetrievalPolicy.hops(bad)


def test_chunk_scores_sum_by_depth_and_seed_mentions_score_one():
    paths = [
        PathHit(names=("A", "B"), rel_types=("적용대상",), evidence_chunk_ids=("c1",)),
        PathHit(names=("A", "B", "C"), rel_types=("x", "y"),
                evidence_chunk_ids=("c1", "c2")),
    ]
    scores = RetrievalPolicy.chunk_scores({"c0": 1}, paths)
    # 씨앗 언급 1.0, 깊이 d 의 관계 근거는 1/(1+d)
    assert scores["c0"] == pytest.approx(1.0)
    assert scores["c1"] == pytest.approx(0.5 + 0.5)
    assert scores["c2"] == pytest.approx(1 / 3)


def test_ranked_chunks_are_capped_and_sorted():
    scores = {f"c{i}": float(i) for i in range(MAX_GRAPH_CHUNKS + 10)}
    ranked = RetrievalPolicy.ranked(scores)
    assert len(ranked) == MAX_GRAPH_CHUNKS
    assert ranked[0] == (f"c{MAX_GRAPH_CHUNKS + 9}", float(MAX_GRAPH_CHUNKS + 9))


def test_path_label_alternates_names_and_relations():
    p = PathHit(names=("A상품", "개인사업자"), rel_types=("적용대상",),
                evidence_chunk_ids=("c1",))
    assert p.label() == ["A상품", "적용대상→", "개인사업자"]


# ── 범위 우선 씨앗 선택(①) ─────────────────────────────────────────────────
def _le(i, score=1.0):
    from src.domain.graph_rag.retrieval import LinkedEntity

    return LinkedEntity(f"e{i}", f"n{i}", "용어", "exact", score)


def test_pick_seeds_prefers_in_scope_then_fills_in_original_order():
    from src.domain.graph_rag.retrieval import MAX_SEEDS

    cands = [_le(i) for i in range(10)]
    seeds = RetrievalPolicy.pick_seeds(cands, {"e7", "e8"}, MAX_SEEDS)
    assert [s.id for s in seeds] == ["e7", "e8", "e0", "e1", "e2"]


def test_pick_seeds_without_scope_keeps_top_n():
    cands = [_le(i) for i in range(10)]
    assert [s.id for s in RetrievalPolicy.pick_seeds(cands, None, 3)] == [
        "e0", "e1", "e2"]


def test_link_candidates_is_wider_than_seeds():
    from src.domain.graph_rag.retrieval import LINK_CANDIDATES, MAX_SEEDS

    assert LINK_CANDIDATES >= MAX_SEEDS * 4
