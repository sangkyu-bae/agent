"""평가 결과 조회 UseCase — 소유권 스코프 포함 (eval-hub Design §2.2, A9).

scope_user_id: None=admin(전체), 그 외=본인 것만. 타인/미존재는 None/False로
동일 응답 → 라우터가 404 은닉.
"""
from src.application.ragas.schemas import EvalResultItem, EvalRunDetailResponse
from src.domain.ragas.entities import EvaluationRun
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
        self,
        run_id: str,
        request_id: str,
        scope_user_id: str | None = None,
    ) -> EvalRunDetailResponse | None:
        run = await self._get_visible_run(run_id, request_id, scope_user_id)
        if run is None:
            return None

        summary = await self._repository.get_run_summary(run_id, request_id)
        return self._to_detail(run, summary)

    async def list_runs(
        self,
        target_type: str | None,
        eval_type: str | None,
        limit: int,
        offset: int,
        request_id: str,
        scope_user_id: str | None = None,
    ) -> tuple[list[EvalRunDetailResponse], int]:
        runs, total = await self._repository.list_runs(
            target_type, eval_type, limit, offset, request_id,
            user_id=scope_user_id,
        )
        return [self._to_detail(r, {}) for r in runs], total

    async def get_results(
        self,
        run_id: str,
        limit: int,
        offset: int,
        request_id: str,
        scope_user_id: str | None = None,
    ) -> tuple[list[EvalResultItem], int]:
        run = await self._get_visible_run(run_id, request_id, scope_user_id)
        if run is None:
            return [], 0
        results, total = await self._repository.get_results_by_run(
            run_id, limit, offset, request_id
        )
        return [self._to_item(r) for r in results], total

    async def delete_run(
        self,
        run_id: str,
        request_id: str,
        scope_user_id: str | None = None,
    ) -> bool:
        run = await self._get_visible_run(run_id, request_id, scope_user_id)
        if run is None:
            return False
        return await self._repository.delete_run(run_id, request_id)

    async def get_recent_realtime(
        self, limit: int, request_id: str, scope_user_id: str | None = None
    ) -> list[EvalResultItem]:
        runs, _ = await self._repository.list_runs(
            target_type=None,
            eval_type="realtime",
            limit=limit,
            offset=0,
            request_id=request_id,
            user_id=scope_user_id,
        )
        items: list[EvalResultItem] = []
        for run in runs:
            results, _ = await self._repository.get_results_by_run(
                run.id, 1, 0, request_id
            )
            items.extend(self._to_item(r) for r in results)
        return items[:limit]

    async def _get_visible_run(
        self, run_id: str, request_id: str, scope_user_id: str | None
    ) -> EvaluationRun | None:
        run = await self._repository.get_run(run_id, request_id)
        if run is None:
            return None
        if scope_user_id is not None and run.user_id != scope_user_id:
            return None  # 타인 자원 — 존재 은닉
        return run

    @staticmethod
    def _to_detail(
        run: EvaluationRun, summary: dict[str, float]
    ) -> EvalRunDetailResponse:
        return EvalRunDetailResponse(
            id=run.id,
            eval_type=run.eval_type,
            target_type=run.target_type,
            status=run.status,
            total_cases=run.total_cases,
            created_at=run.created_at,
            completed_at=run.completed_at,
            summary=summary,
            error_message=run.error_message,
            config=run.config or {},
        )

    @staticmethod
    def _to_item(r) -> EvalResultItem:
        return EvalResultItem(
            id=r.id,
            question=r.question,
            answer=r.answer,
            ground_truth=r.ground_truth,
            contexts=r.contexts,
            scores=r.metrics,
            created_at=r.created_at,
        )
