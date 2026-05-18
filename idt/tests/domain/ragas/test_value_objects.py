"""Value Objects 단위 테스트."""
import pytest

from src.domain.ragas.value_objects import EvalConfig, MetricScore, MetricType, TestCase


class TestMetricType:
    def test_all_metric_types_defined(self) -> None:
        expected = {
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
            "answer_correctness",
            "answer_similarity",
            "hit_rate",
            "mrr",
            "ndcg",
        }
        assert {m.value for m in MetricType} == expected

    def test_metric_type_is_string_enum(self) -> None:
        assert MetricType.FAITHFULNESS == "faithfulness"
        assert isinstance(MetricType.FAITHFULNESS, str)


class TestMetricScore:
    def test_valid_score(self) -> None:
        score = MetricScore(metric=MetricType.FAITHFULNESS, score=0.85)
        assert score.metric == MetricType.FAITHFULNESS
        assert score.score == 0.85

    def test_boundary_scores(self) -> None:
        MetricScore(metric=MetricType.MRR, score=0.0)
        MetricScore(metric=MetricType.MRR, score=1.0)

    def test_score_below_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="0.0~1.0"):
            MetricScore(metric=MetricType.MRR, score=-0.1)

    def test_score_above_one_raises(self) -> None:
        with pytest.raises(ValueError, match="0.0~1.0"):
            MetricScore(metric=MetricType.MRR, score=1.1)

    def test_frozen(self) -> None:
        score = MetricScore(metric=MetricType.FAITHFULNESS, score=0.5)
        with pytest.raises(AttributeError):
            score.score = 0.9  # type: ignore[misc]


class TestTestCase:
    def test_minimal_test_case(self) -> None:
        tc = TestCase(question="질문")
        assert tc.question == "질문"
        assert tc.ground_truth is None
        assert tc.expected_contexts == []
        assert tc.metadata == {}

    def test_full_test_case(self) -> None:
        tc = TestCase(
            question="대출 한도는?",
            ground_truth="최대 5억원",
            expected_contexts=["doc1", "doc2"],
            metadata={"category": "loan"},
        )
        assert tc.ground_truth == "최대 5억원"
        assert len(tc.expected_contexts) == 2

    def test_frozen(self) -> None:
        tc = TestCase(question="q")
        with pytest.raises(AttributeError):
            tc.question = "new"  # type: ignore[misc]


class TestEvalConfig:
    def test_defaults(self) -> None:
        cfg = EvalConfig(metrics=[MetricType.FAITHFULNESS])
        assert cfg.top_k == 5
        assert cfg.sample_ratio == 1.0
        assert cfg.llm_model == "gpt-4o-mini"
        assert cfg.collection_name is None
        assert cfg.agent_id is None

    def test_custom_config(self) -> None:
        cfg = EvalConfig(
            metrics=[MetricType.FAITHFULNESS, MetricType.ANSWER_RELEVANCY],
            top_k=10,
            sample_ratio=0.5,
            llm_model="gpt-4o",
            agent_id="agent-123",
        )
        assert len(cfg.metrics) == 2
        assert cfg.top_k == 10
        assert cfg.agent_id == "agent-123"

    def test_frozen(self) -> None:
        cfg = EvalConfig(metrics=[MetricType.MRR])
        with pytest.raises(AttributeError):
            cfg.top_k = 20  # type: ignore[misc]
