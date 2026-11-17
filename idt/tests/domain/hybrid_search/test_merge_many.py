"""RRFFusionPolicy.merge_many — 최종 결과에 보조 목록을 한 번 더 합친다.

graph-rag-foundation Design §2.2 (검색): 기존 merge 는 그대로 두고 추가만 한다.
"""
from src.domain.hybrid_search.policies import RankedList, RRFFusionPolicy
from src.domain.hybrid_search.schemas import HybridSearchResult


def _r(id_: str, source: str = "both", score: float = 0.1) -> HybridSearchResult:
    return HybridSearchResult(
        id=id_, content=f"c-{id_}", score=score, bm25_rank=1, bm25_score=2.0,
        vector_rank=1, vector_score=0.9, source=source, metadata={"document_id": "d"},
    )


def _g(id_: str) -> HybridSearchResult:
    return HybridSearchResult(
        id=id_, content=f"g-{id_}", score=0.7, bm25_rank=None, bm25_score=None,
        vector_rank=None, vector_score=None, source="graph", metadata={"document_id": "g"},
    )


def test_empty_supplemental_keeps_order_and_source():
    primary = [_r("a"), _r("b", "bm25_only"), _r("c", "vector_only")]
    out = RRFFusionPolicy().merge_many(
        [RankedList("primary", primary, 1.0), RankedList("graph", [], 0.5)], top_k=5
    )
    assert [r.id for r in out] == ["a", "b", "c"]
    assert [r.source for r in out] == ["both", "bm25_only", "vector_only"]


def test_overlap_marks_combined_source_and_keeps_primary_fields():
    primary = [_r("a"), _r("b", "bm25_only")]
    graph = [_g("b"), _g("z")]
    out = RRFFusionPolicy().merge_many(
        [RankedList("primary", primary, 1.0), RankedList("graph", graph, 0.5)], top_k=5
    )
    by_id = {r.id: r for r in out}
    assert by_id["b"].source == "bm25_only+graph"
    assert by_id["b"].content == "c-b"          # primary 본문 유지
    assert by_id["b"].bm25_score == 2.0         # primary 개별 점수 유지
    assert by_id["z"].source == "graph"
    assert by_id["z"].bm25_rank is None
    assert len(by_id["b"].source) <= 20         # ai_retrieval_source.fusion_source VARCHAR(20)


def test_scores_are_weighted_rrf():
    k = 60
    primary = [_r("a"), _r("b")]
    graph = [_g("b")]
    out = RRFFusionPolicy().merge_many(
        [RankedList("primary", primary, 1.0), RankedList("graph", graph, 0.5)],
        top_k=5, k=k,
    )
    by_id = {r.id: r for r in out}
    assert abs(by_id["a"].score - 1.0 / (k + 1)) < 1e-12
    assert abs(by_id["b"].score - (1.0 / (k + 2) + 0.5 / (k + 1))) < 1e-12
    assert out[0].id == "b"  # 두 목록에 모두 있는 청크가 올라온다


def test_top_k_truncates():
    primary = [_r(str(i)) for i in range(5)]
    graph = [_g(f"g{i}") for i in range(5)]
    out = RRFFusionPolicy().merge_many(
        [RankedList("primary", primary, 1.0), RankedList("graph", graph, 0.5)], top_k=3
    )
    assert len(out) == 3


def test_all_empty_returns_empty():
    out = RRFFusionPolicy().merge_many(
        [RankedList("primary", [], 1.0), RankedList("graph", [], 0.5)], top_k=5
    )
    assert out == []


def test_graph_only_when_primary_empty():
    out = RRFFusionPolicy().merge_many(
        [RankedList("primary", [], 1.0), RankedList("graph", [_g("x")], 0.5)], top_k=5
    )
    assert [(r.id, r.source) for r in out] == [("x", "graph")]


def test_duplicate_ids_within_one_list_use_best_rank():
    primary = [_r("a"), _r("a"), _r("b")]
    out = RRFFusionPolicy().merge_many([RankedList("primary", primary, 1.0)], top_k=5)
    assert [r.id for r in out] == ["a", "b"]
