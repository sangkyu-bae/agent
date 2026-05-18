"""RetrievalMetricCalculator 단위 테스트."""
import math

import pytest

from src.infrastructure.ragas.retrieval_metric_calculator import RetrievalMetricCalculator


class TestHitRate:
    def test_hit(self) -> None:
        assert RetrievalMetricCalculator.hit_rate(["a", "b", "c"], ["b"]) == 1.0

    def test_miss(self) -> None:
        assert RetrievalMetricCalculator.hit_rate(["a", "b", "c"], ["d"]) == 0.0

    def test_empty_retrieved(self) -> None:
        assert RetrievalMetricCalculator.hit_rate([], ["a"]) == 0.0

    def test_empty_relevant(self) -> None:
        assert RetrievalMetricCalculator.hit_rate(["a"], []) == 0.0

    def test_multiple_relevant(self) -> None:
        assert RetrievalMetricCalculator.hit_rate(["a", "b"], ["b", "c"]) == 1.0


class TestMRR:
    def test_first_position(self) -> None:
        assert RetrievalMetricCalculator.mrr(["a", "b", "c"], ["a"]) == 1.0

    def test_second_position(self) -> None:
        assert RetrievalMetricCalculator.mrr(["a", "b", "c"], ["b"]) == 0.5

    def test_third_position(self) -> None:
        result = RetrievalMetricCalculator.mrr(["a", "b", "c"], ["c"])
        assert abs(result - 1 / 3) < 1e-9

    def test_no_match(self) -> None:
        assert RetrievalMetricCalculator.mrr(["a", "b"], ["d"]) == 0.0

    def test_empty_retrieved(self) -> None:
        assert RetrievalMetricCalculator.mrr([], ["a"]) == 0.0

    def test_multiple_relevant_returns_best_rank(self) -> None:
        assert RetrievalMetricCalculator.mrr(["a", "b", "c"], ["b", "c"]) == 0.5


class TestNDCG:
    def test_perfect_ranking(self) -> None:
        result = RetrievalMetricCalculator.ndcg(["a", "b"], ["a", "b"])
        assert abs(result - 1.0) < 1e-9

    def test_no_relevant(self) -> None:
        assert RetrievalMetricCalculator.ndcg(["a", "b"], ["c"]) == 0.0

    def test_empty_retrieved(self) -> None:
        assert RetrievalMetricCalculator.ndcg([], ["a"]) == 0.0

    def test_empty_relevant(self) -> None:
        assert RetrievalMetricCalculator.ndcg(["a"], []) == 0.0

    def test_partial_match(self) -> None:
        result = RetrievalMetricCalculator.ndcg(["a", "b", "c"], ["b"])
        assert 0.0 < result < 1.0

    def test_with_k(self) -> None:
        result = RetrievalMetricCalculator.ndcg(["a", "b", "c"], ["c"], k=2)
        assert result == 0.0

    def test_k_larger_than_list(self) -> None:
        result = RetrievalMetricCalculator.ndcg(["a", "b"], ["a", "b"], k=10)
        assert abs(result - 1.0) < 1e-9
