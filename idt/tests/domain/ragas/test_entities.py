"""EvaluationRun, EvaluationResult 엔티티 단위 테스트."""
from datetime import datetime, timezone

from src.domain.ragas.entities import EvaluationResult, EvaluationRun


class TestEvaluationRun:
    def _make_run(self, **overrides) -> EvaluationRun:
        defaults = dict(
            id="run-1",
            eval_type="batch",
            target_type="rag",
            status="pending",
            total_cases=10,
            created_at=datetime(2026, 5, 13, tzinfo=timezone.utc),
        )
        defaults.update(overrides)
        return EvaluationRun(**defaults)

    def test_create_minimal(self) -> None:
        run = self._make_run()
        assert run.id == "run-1"
        assert run.status == "pending"
        assert run.target_id is None
        assert run.config == {}
        assert run.completed_at is None
        assert run.error_message is None

    def test_mark_completed(self) -> None:
        run = self._make_run(status="running")
        done_at = datetime(2026, 5, 13, 1, 0, tzinfo=timezone.utc)
        run.mark_completed(done_at)
        assert run.status == "completed"
        assert run.completed_at == done_at

    def test_mark_failed(self) -> None:
        run = self._make_run(status="running")
        failed_at = datetime(2026, 5, 13, 1, 0, tzinfo=timezone.utc)
        run.mark_failed("timeout", failed_at)
        assert run.status == "failed"
        assert run.error_message == "timeout"
        assert run.completed_at == failed_at

    def test_config_default_is_empty_dict(self) -> None:
        run = self._make_run()
        assert run.config == {}
        run.config["key"] = "value"
        run2 = self._make_run()
        assert run2.config == {}


class TestEvaluationResult:
    def _make_result(self, **overrides) -> EvaluationResult:
        defaults = dict(
            id="res-1",
            run_id="run-1",
            question="대출 한도는?",
            answer="최대 5억원입니다.",
            contexts=["문서1 내용", "문서2 내용"],
            created_at=datetime(2026, 5, 13, tzinfo=timezone.utc),
        )
        defaults.update(overrides)
        return EvaluationResult(**defaults)

    def test_create_minimal(self) -> None:
        result = self._make_result()
        assert result.question == "대출 한도는?"
        assert result.ground_truth is None
        assert result.metrics == {}

    def test_with_metrics(self) -> None:
        result = self._make_result(
            metrics={"faithfulness": 0.9, "answer_relevancy": 0.85}
        )
        assert result.metrics["faithfulness"] == 0.9
        assert len(result.metrics) == 2

    def test_with_ground_truth(self) -> None:
        result = self._make_result(ground_truth="최대 5억원")
        assert result.ground_truth == "최대 5억원"

    def test_metrics_default_is_empty_dict(self) -> None:
        r1 = self._make_result()
        r1.metrics["key"] = 0.5
        r2 = self._make_result()
        assert r2.metrics == {}
