"""평가 결과 조회 UseCase."""
from src.application.ragas.schemas import EvalResultItem, EvalRunDetailResponse
from src.domain.ragas.interfaces import EvaluationRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class EvalResultUseCase:
    def __init__(
        self,
        repository: EvaluationRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def get_run_detail(
        self, run_id: str, request_id: str
    ) -> EvalRunDetailResponse | None:
        run = await self._repository.get_run(run_id, request_id)
        if run is None:
            return None

        summary = await self._repository.get_run_summary(run_id, request_id)

        return EvalRunDetailResponse(
            id=run.id,
            eval_type=run.eval_type,
            target_type=run.target_type,
            status=run.status,
            total_cases=run.total_cases,
            created_at=run.created_at,
            completed_at=run.completed_at,
            summary=summary,
        )

    async def list_runs(
        self,
        target_type: str | None,
        eval_type: str | None,
        limit: int,
        offset: int,
        request_id: str,
    ) -> tuple[list[EvalRunDetailResponse], int]:
        runs, total = await self._repository.list_runs(
            target_type, eval_type, limit, offset, request_id
        )
        items = [
            EvalRunDetailResponse(
                id=r.id,
                eval_type=r.eval_type,
                target_type=r.target_type,
                status=r.status,
                total_cases=r.total_cases,
                created_at=r.created_at,
                completed_at=r.completed_at,
                summary={},
            )
            for r in runs
        ]
        return items, total

    async def get_results(
        self, run_id: str, limit: int, offset: int, request_id: str
    ) -> tuple[list[EvalResultItem], int]:
        results, total = await self._repository.get_results_by_run(
            run_id, limit, offset, request_id
        )
        items = [
            EvalResultItem(
                id=r.id,
                question=r.question,
                answer=r.answer,
                ground_truth=r.ground_truth,
                scores=r.metrics,
                created_at=r.created_at,
            )
            for r in results
        ]
        return items, total

    async def delete_run(self, run_id: str, request_id: str) -> bool:
        return await self._repository.delete_run(run_id, request_id)

    async def get_recent_realtime(
        self, limit: int, request_id: str
    ) -> list[EvalResultItem]:
        runs, _ = await self._repository.list_runs(
            target_type=None,
            eval_type="realtime",
            limit=limit,
            offset=0,
            request_id=request_id,
        )
        items: list[EvalResultItem] = []
        for run in runs:
            results, _ = await self._repository.get_results_by_run(
                run.id, 1, 0, request_id
            )
            for r in results:
                items.append(
                    EvalResultItem(
                        id=r.id,
                        question=r.question,
                        answer=r.answer,
                        ground_truth=r.ground_truth,
                        scores=r.metrics,
                        created_at=r.created_at,
                    )
                )
        return items[:limit]
