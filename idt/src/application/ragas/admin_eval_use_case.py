"""Admin RAGAS 평가 대시보드 UseCase."""
from src.application.ragas.admin_schemas import (
    DashboardStatsResponse,
    RunWithResultsResponse,
)
from src.application.ragas.schemas import EvalResultItem, EvalRunDetailResponse
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.ragas.interfaces import EvaluationRepositoryInterface


class AdminEvalUseCase:
    def __init__(
        self,
        repository: EvaluationRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def get_dashboard_stats(
        self, recent_limit: int, request_id: str
    ) -> DashboardStatsResponse:
        self._logger.info(
            "Admin dashboard stats requested",
            request_id=request_id,
            recent_limit=recent_limit,
        )
        stats = await self._repository.get_dashboard_stats(
            recent_limit, request_id
        )

        recent_runs = []
        for run in stats["recent_runs"]:
            summary = await self._repository.get_run_summary(run.id, request_id)
            recent_runs.append(
                EvalRunDetailResponse(
                    id=run.id,
                    eval_type=run.eval_type,
                    target_type=run.target_type,
                    status=run.status,
                    total_cases=run.total_cases,
                    created_at=run.created_at,
                    completed_at=run.completed_at,
                    summary=summary,
                )
            )

        return DashboardStatsResponse(
            total_runs=stats["total_runs"],
            status_counts=stats["status_counts"],
            target_type_counts=stats["target_type_counts"],
            avg_metrics=stats["avg_metrics"],
            recent_runs=recent_runs,
        )

    async def list_runs_with_summary(
        self,
        target_type: str | None,
        eval_type: str | None,
        status: str | None,
        limit: int,
        offset: int,
        request_id: str,
    ) -> tuple[list[EvalRunDetailResponse], int]:
        items, total = await self._repository.list_runs_with_summary(
            target_type, eval_type, status, limit, offset, request_id
        )
        return [
            EvalRunDetailResponse(
                id=i["id"],
                eval_type=i["eval_type"],
                target_type=i["target_type"],
                status=i["status"],
                total_cases=i["total_cases"],
                created_at=i["created_at"],
                completed_at=i["completed_at"],
                summary=i.get("summary", {}),
            )
            for i in items
        ], total

    async def get_run_with_results(
        self, run_id: str, request_id: str
    ) -> RunWithResultsResponse | None:
        run = await self._repository.get_run(run_id, request_id)
        if run is None:
            return None

        summary = await self._repository.get_run_summary(run_id, request_id)
        results, results_total = await self._repository.get_results_by_run(
            run_id, limit=100, offset=0, request_id=request_id
        )

        return RunWithResultsResponse(
            id=run.id,
            eval_type=run.eval_type,
            target_type=run.target_type,
            status=run.status,
            total_cases=run.total_cases,
            config=run.config,
            created_at=run.created_at,
            completed_at=run.completed_at,
            summary=summary,
            results=[
                EvalResultItem(
                    id=r.id,
                    question=r.question,
                    answer=r.answer,
                    ground_truth=r.ground_truth,
                    contexts=r.contexts,
                    scores=r.metrics,
                    created_at=r.created_at,
                )
                for r in results
            ],
            results_total=results_total,
        )

    async def list_testsets(
        self, limit: int, offset: int, request_id: str
    ) -> tuple[list[dict], int]:
        return await self._repository.list_testsets(limit, offset, request_id)
