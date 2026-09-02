"""SweepPolicy 단위 테스트.

Design Ref: §3.1 / D7 — 모델 최대 5개, 순차 실행.
Design Ref: §3.1 / D9 — temperature는 재현성을 위해 0.0 고정.
Design Ref: §6.1 — 검증 실패는 errors 리스트로 모아 400으로 변환한다
                   (EvaluationPolicy.validate_config 선례).
"""
import pytest

from src.domain.eval_sweep.policies import SweepPolicy
from src.domain.ragas.value_objects import MetricType

# agent 대상이 지원하는 메트릭 (domain/ragas/policies.py TARGET_METRICS["agent"])
AGENT_METRICS = [MetricType.ANSWER_RELEVANCY]


def _validate(**overrides):
    kwargs = {
        "model_ids": ["m-1", "m-2"],
        "judge_llm_model_id": "m-judge",
        "metrics": AGENT_METRICS,
        "testset_case_count": 10,
    }
    kwargs.update(overrides)
    return SweepPolicy.validate(**kwargs)


class TestConstants:
    def test_max_models_is_five(self):
        assert SweepPolicy.MAX_MODELS == 5

    def test_temperature_is_fixed_to_zero(self):
        """D9 — 재현성 NFR(편차 ≤5%p)의 최소 조건."""
        assert SweepPolicy.FIXED_TEMPERATURE == 0.0


class TestValidPayload:
    def test_returns_no_errors(self):
        assert _validate() == []

    def test_exactly_five_models_is_allowed(self):
        assert _validate(model_ids=[f"m-{i}" for i in range(5)]) == []

    def test_single_model_is_allowed(self):
        assert _validate(model_ids=["m-1"]) == []


class TestModelSelection:
    def test_empty_model_list_is_rejected(self):
        errors = _validate(model_ids=[])

        assert len(errors) == 1
        assert "최소 1개" in errors[0]

    def test_more_than_max_models_is_rejected(self):
        errors = _validate(model_ids=[f"m-{i}" for i in range(6)])

        assert len(errors) == 1
        assert "최대 5개" in errors[0]
        assert "6" in errors[0], "선택한 개수를 메시지에 담아야 한다"

    def test_duplicate_models_are_rejected(self):
        errors = _validate(model_ids=["m-1", "m-1", "m-2"])

        assert len(errors) == 1
        assert "중복" in errors[0]


class TestJudgeModel:
    @pytest.mark.parametrize("judge", [None, "", "   "])
    def test_missing_judge_is_rejected(self, judge):
        errors = _validate(judge_llm_model_id=judge)

        assert len(errors) == 1
        assert "judge" in errors[0].lower()


class TestMetrics:
    def test_empty_metrics_is_rejected(self):
        errors = _validate(metrics=[])

        assert len(errors) == 1
        assert "지표" in errors[0]

    def test_metrics_unsupported_by_agent_target_are_rejected(self):
        """스윕은 agent 대상 전용 — faithfulness/context_* 는 지원되지 않는다.

        검증은 EvaluationPolicy.validate_metrics_for_target("agent", ...)에 위임한다.
        """
        errors = _validate(metrics=[MetricType.FAITHFULNESS])

        assert len(errors) == 1
        assert "faithfulness" in errors[0]

    def test_agent_supported_metrics_pass(self):
        errors = _validate(metrics=[
            MetricType.ANSWER_RELEVANCY,
            MetricType.ANSWER_CORRECTNESS,
            MetricType.ANSWER_SIMILARITY,
        ])

        assert errors == []


class TestTestset:
    @pytest.mark.parametrize("count", [0, -1])
    def test_empty_testset_is_rejected(self, count):
        errors = _validate(testset_case_count=count)

        assert len(errors) == 1
        assert "케이스" in errors[0]


class TestErrorAccumulation:
    def test_all_violations_are_reported_together(self):
        """한 번에 모아 보여줘야 사용자가 왕복하지 않는다."""
        errors = _validate(
            model_ids=[f"m-{i}" for i in range(6)],
            judge_llm_model_id=None,
            metrics=[],
            testset_case_count=0,
        )

        assert len(errors) == 4


class TestTotalRuns:
    def test_total_runs_equals_model_count(self):
        """스윕 1건 = 모델 수만큼의 evaluation_run (§2.2 데이터 흐름)."""
        assert SweepPolicy.total_runs(["m-1", "m-2", "m-3"]) == 3
