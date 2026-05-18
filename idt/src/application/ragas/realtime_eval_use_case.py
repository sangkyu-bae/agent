"""실시간 단건 평가 UseCase."""
import uuid
from datetime import datetime, timezone

from src.application.ragas.schemas import RealtimeEvalRequest, RealtimeEvalResponse
from src.domain.ragas.entities import EvaluationResult, EvaluationRun
from src.domain.ragas.interfaces import EvaluationRepositoryInterface, EvaluatorInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class RealtimeEvaluationUseCase:
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
        self, request: RealtimeEvalRequest, request_id: str
    ) -> RealtimeEvalResponse:
        self._logger.info(
            "Realtime evaluation start",
            request_id=request_id,
            metrics=request.metrics,
        )

        run = EvaluationRun(
            id=str(uuid.uuid4()),
            eval_type="realtime",
            target_type=request.target_type,
            status="running",
            total_cases=1,
            created_at=datetime.now(timezone.utc),
        )
        await self._repository.save_run(run, request_id)

        scores = await self._evaluator.evaluate(
            question=request.question,
            answer=request.answer,
            contexts=request.contexts,
            ground_truth=request.ground_truth,
            metrics=request.metrics,
            request_id=request_id,
        )

        result_id = str(uuid.uuid4())
        result = EvaluationResult(
            id=result_id,
            run_id=run.id,
            question=request.question,
            answer=request.answer,
            contexts=request.contexts,
            ground_truth=request.ground_truth,
            metrics=scores,
            created_at=datetime.now(timezone.utc),
        )
        await self._repository.save_result(result, request_id)

        run.mark_completed(datetime.now(timezone.utc))
        await self._repository.update_run(run, request_id)

        return RealtimeEvalResponse(result_id=result_id, scores=scores)
