"""EvaluationPolicy 단위 테스트."""
import pytest

from src.domain.ragas.policies import EvaluationPolicy
from src.domain.ragas.value_objects import EvalConfig, MetricType, TestCase


class TestValidateConfig:
    def test_valid_config(self) -> None:
        cfg = EvalConfig(metrics=[MetricType.FAITHFULNESS], top_k=5)
        errors = EvaluationPolicy.validate_config(cfg)
        assert errors == []

    def test_empty_metrics(self) -> None:
        cfg = EvalConfig(metrics=[])
        errors = EvaluationPolicy.validate_config(cfg)
        assert any("1개 이상" in e for e in errors)

    def test_top_k_zero(self) -> None:
        cfg = EvalConfig(metrics=[MetricType.MRR], top_k=0)
        errors = EvaluationPolicy.validate_config(cfg)
        assert any("top_k" in e for e in errors)

    def test_sample_ratio_zero(self) -> None:
        cfg = EvalConfig(metrics=[MetricType.MRR], sample_ratio=0.0)
        errors = EvaluationPolicy.validate_config(cfg)
        assert any("sample_ratio" in e for e in errors)

    def test_sample_ratio_over_one(self) -> None:
        cfg = EvalConfig(metrics=[MetricType.MRR], sample_ratio=1.5)
        errors = EvaluationPolicy.validate_config(cfg)
        assert any("sample_ratio" in e for e in errors)


class TestValidateTestcases:
    def _cfg(self, *metrics: MetricType) -> EvalConfig:
        return EvalConfig(metrics=list(metrics))

    def test_empty_cases(self) -> None:
        errors = EvaluationPolicy.validate_testcases(
            [], self._cfg(MetricType.FAITHFULNESS)
        )
        assert any("비어있습니다" in e for e in errors)

    def test_blank_question(self) -> None:
        cases = [TestCase(question="  ")]
        errors = EvaluationPolicy.validate_testcases(
            cases, self._cfg(MetricType.FAITHFULNESS)
        )
        assert any("질문이 비어있습니다" in e for e in errors)

    def test_gt_required_but_missing(self) -> None:
        cases = [TestCase(question="대출 한도?")]
        errors = EvaluationPolicy.validate_testcases(
            cases, self._cfg(MetricType.CONTEXT_RECALL)
        )
        assert any("ground_truth" in e for e in errors)

    def test_gt_not_required_for_faithfulness(self) -> None:
        cases = [TestCase(question="대출 한도?")]
        errors = EvaluationPolicy.validate_testcases(
            cases, self._cfg(MetricType.FAITHFULNESS)
        )
        assert errors == []

    def test_valid_with_gt(self) -> None:
        cases = [TestCase(question="대출 한도?", ground_truth="최대 5억원")]
        errors = EvaluationPolicy.validate_testcases(
            cases, self._cfg(MetricType.ANSWER_CORRECTNESS)
        )
        assert errors == []


class TestRequiresGroundTruth:
    def test_faithfulness_no_gt(self) -> None:
        assert not EvaluationPolicy.requires_ground_truth([MetricType.FAITHFULNESS])

    def test_context_recall_needs_gt(self) -> None:
        assert EvaluationPolicy.requires_ground_truth([MetricType.CONTEXT_RECALL])

    def test_answer_correctness_needs_gt(self) -> None:
        assert EvaluationPolicy.requires_ground_truth([MetricType.ANSWER_CORRECTNESS])

    def test_mixed_metrics(self) -> None:
        assert EvaluationPolicy.requires_ground_truth(
            [MetricType.FAITHFULNESS, MetricType.ANSWER_SIMILARITY]
        )


class TestIsPassing:
    def test_empty_scores(self) -> None:
        assert not EvaluationPolicy.is_passing({})

    def test_passing(self) -> None:
        assert EvaluationPolicy.is_passing({"f": 0.8, "ar": 0.9})

    def test_failing(self) -> None:
        assert not EvaluationPolicy.is_passing({"f": 0.5, "ar": 0.6})

    def test_custom_threshold(self) -> None:
        assert EvaluationPolicy.is_passing({"f": 0.5}, threshold=0.5)
        assert not EvaluationPolicy.is_passing({"f": 0.49}, threshold=0.5)
