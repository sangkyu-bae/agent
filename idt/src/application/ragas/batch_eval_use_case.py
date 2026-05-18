"""배치 평가 UseCase."""
import random
import uuid
from datetime import datetime, timezone

from src.application.ragas.schemas import BatchEvalRequest, BatchEvalResponse
from src.domain.ragas.entities import EvaluationResult, EvaluationRun
from src.domain.ragas.interfaces import EvaluationRepositoryInterface, EvaluatorInterface
from src.domain.ragas.policies import EvaluationPolicy
from src.domain.ragas.value_objects import EvalConfig, MetricType, TestCase
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class BatchEvaluationUseCase:
    def __init__(
        self,
        repository: EvaluationRepositoryInterface,
        evaluator: EvaluatorInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._evaluator = evaluator
        self._logger = logger

    async def execute(
        self,
        request: BatchEvalRequest,
        request_id: str,
    ) -> BatchEvalResponse:
        config = EvalConfig(
            metrics=[MetricType(m) for m in request.metrics],
            top_k=request.top_k,
            sample_ratio=request.sample_ratio,
            llm_model=request.llm_model,
            agent_id=request.agent_id,
            collection_name=request.collection_name,
        )

        config_errors = EvaluationPolicy.validate_config(config)
        if config_errors:
            raise ValueError("; ".join(config_errors))

        testcases = [
            TestCase(
                question=tc["question"],
                ground_truth=tc.get("ground_truth"),
                expected_contexts=tc.get("expected_contexts", []),
                metadata=tc.get("metadata", {}),
            )
            for tc in request.testcases
        ]

        case_errors = EvaluationPolicy.validate_testcases(testcases, config)
        if case_errors:
            raise ValueError("; ".join(case_errors))

        if config.sample_ratio < 1.0:
            sample_size = max(1, int(len(testcases) * config.sample_ratio))
            testcases = random.sample(testcases, sample_size)

        run = EvaluationRun(
            id=str(uuid.uuid4()),
            eval_type="batch",
            target_type=request.target_type,
            target_id=request.agent_id,
            status="pending",
            total_cases=len(testcases),
            config={
                "metrics": request.metrics,
                "top_k": request.top_k,
                "llm_model": request.llm_model,
            },
            created_at=datetime.now(timezone.utc),
        )
        await self._repository.save_run(run, request_id)

        return BatchEvalResponse(
            run_id=run.id,
            status=run.status,
            total_cases=run.total_cases,
            message="배치 평가가 등록되었습니다.",
        )

    async def run_evaluation(
        self,
        run_id: str,
        testcases: list[TestCase],
        metrics: list[str],
        request_id: str,
    ) -> None:
        run = await self._repository.get_run(run_id, request_id)
        if run is None:
            self._logger.error("Run not found", request_id=request_id, run_id=run_id)
            return

        run.status = "running"
        await self._repository.update_run(run, request_id)

        try:
            results: list[EvaluationResult] = []
            for tc in testcases:
                scores = await self._evaluator.evaluate(
                    question=tc.question,
                    answer="",
                    contexts=[],
                    ground_truth=tc.ground_truth,
                    metrics=metrics,
                    request_id=request_id,
                )
                result = EvaluationResult(
                    id=str(uuid.uuid4()),
                    run_id=run_id,
                    question=tc.question,
                    answer="",
                    contexts=[],
                    ground_truth=tc.ground_truth,
                    metrics=scores,
                    created_at=datetime.now(timezone.utc),
                )
                results.append(result)

            if results:
                await self._repository.save_results_bulk(results, request_id)

            run.mark_completed(datetime.now(timezone.utc))
            await self._repository.update_run(run, request_id)

        except Exception as e:
            self._logger.exception(
                "Batch evaluation failed", request_id=request_id, run_id=run_id
            )
            run.mark_failed(str(e), datetime.now(timezone.utc))
            await self._repository.update_run(run, request_id)
