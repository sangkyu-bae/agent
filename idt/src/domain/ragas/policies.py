"""RAGAS 평가 실행 정책."""
from src.domain.ragas.value_objects import EvalConfig, MetricType, TestCase

METRICS_REQUIRING_GROUND_TRUTH = {
    MetricType.CONTEXT_RECALL,
    MetricType.ANSWER_CORRECTNESS,
    MetricType.ANSWER_SIMILARITY,
}

# 대상 유형별 적용 가능 메트릭 SoT — 카탈로그 API(A7)와 배치 실행 검증(A8)이 공유.
# agent는 검색 컨텍스트가 없어 context/faithfulness 계열 제외.
# 실제 계산기 대응: RAGAS_METRICS→RagasEvaluatorAdapter, RETRIEVAL_RANK_METRICS→RetrievalMetricCalculator
TARGET_METRICS: dict[str, list[MetricType]] = {
    "rag": [
        MetricType.FAITHFULNESS,
        MetricType.ANSWER_RELEVANCY,
        MetricType.CONTEXT_PRECISION,
        MetricType.CONTEXT_RECALL,
        MetricType.ANSWER_CORRECTNESS,
        MetricType.ANSWER_SIMILARITY,
    ],
    "agent": [
        MetricType.ANSWER_RELEVANCY,
        MetricType.ANSWER_CORRECTNESS,
        MetricType.ANSWER_SIMILARITY,
    ],
    "retrieval": [
        MetricType.HIT_RATE,
        MetricType.MRR,
        MetricType.NDCG,
        MetricType.CONTEXT_PRECISION,
        MetricType.CONTEXT_RECALL,
    ],
}

# RAGAS 라이브러리로 계산하는 메트릭 (그 외는 순위 계산기 담당)
RAGAS_METRICS = {
    MetricType.FAITHFULNESS,
    MetricType.ANSWER_RELEVANCY,
    MetricType.CONTEXT_PRECISION,
    MetricType.CONTEXT_RECALL,
    MetricType.ANSWER_CORRECTNESS,
    MetricType.ANSWER_SIMILARITY,
}

RETRIEVAL_RANK_METRICS = {MetricType.HIT_RATE, MetricType.MRR, MetricType.NDCG}


class EvaluationPolicy:
    """평가 실행 정책."""

    @staticmethod
    def validate_config(config: EvalConfig) -> list[str]:
        errors: list[str] = []
        if not config.metrics:
            errors.append("최소 1개 이상의 평가 지표가 필요합니다")
        if config.top_k < 1:
            errors.append("top_k는 1 이상이어야 합니다")
        if not 0.0 < config.sample_ratio <= 1.0:
            errors.append("sample_ratio는 0.0 초과 1.0 이하여야 합니다")
        return errors

    @staticmethod
    def validate_testcases(
        cases: list[TestCase], config: EvalConfig
    ) -> list[str]:
        errors: list[str] = []
        if not cases:
            errors.append("테스트 케이스가 비어있습니다")
            return errors

        needs_gt = bool(METRICS_REQUIRING_GROUND_TRUTH & set(config.metrics))
        for i, case in enumerate(cases):
            if not case.question.strip():
                errors.append(f"케이스 {i}: 질문이 비어있습니다")
            if needs_gt and not case.ground_truth:
                errors.append(
                    f"케이스 {i}: 선택한 지표에 ground_truth가 필요합니다"
                )
        return errors

    @staticmethod
    def requires_ground_truth(metrics: list[MetricType]) -> bool:
        return bool(METRICS_REQUIRING_GROUND_TRUTH & set(metrics))

    @staticmethod
    def validate_metrics_for_target(
        target_type: str, metrics: list[MetricType]
    ) -> list[str]:
        allowed = set(TARGET_METRICS.get(target_type, []))
        invalid = [m.value for m in metrics if m not in allowed]
        if invalid:
            return [
                f"{target_type} 대상에서 지원하지 않는 메트릭: {', '.join(invalid)}"
            ]
        return []

    @staticmethod
    def is_passing(scores: dict[str, float], threshold: float = 0.7) -> bool:
        if not scores:
            return False
        avg = sum(scores.values()) / len(scores)
        return avg >= threshold
