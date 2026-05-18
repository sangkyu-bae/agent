"""커스텀 Retrieval 품질 지표 계산기."""
import math


class RetrievalMetricCalculator:
    """Hit Rate, MRR, NDCG 계산."""

    @staticmethod
    def hit_rate(retrieved_ids: list[str], relevant_ids: list[str]) -> float:
        if not retrieved_ids or not relevant_ids:
            return 0.0
        relevant_set = set(relevant_ids)
        return 1.0 if any(rid in relevant_set for rid in retrieved_ids) else 0.0

    @staticmethod
    def mrr(retrieved_ids: list[str], relevant_ids: list[str]) -> float:
        if not retrieved_ids or not relevant_ids:
            return 0.0
        relevant_set = set(relevant_ids)
        for i, rid in enumerate(retrieved_ids):
            if rid in relevant_set:
                return 1.0 / (i + 1)
        return 0.0

    @staticmethod
    def ndcg(
        retrieved_ids: list[str],
        relevant_ids: list[str],
        k: int | None = None,
    ) -> float:
        if not retrieved_ids or not relevant_ids:
            return 0.0

        relevant_set = set(relevant_ids)
        top = retrieved_ids[:k] if k is not None else retrieved_ids

        dcg = sum(
            1.0 / math.log2(i + 2)
            for i, rid in enumerate(top)
            if rid in relevant_set
        )

        ideal_count = min(len(relevant_set), len(top))
        idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_count))

        if idcg == 0.0:
            return 0.0
        return dcg / idcg
