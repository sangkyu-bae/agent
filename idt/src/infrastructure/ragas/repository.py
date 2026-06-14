"""RAGAS 평가 결과 MySQL 저장소."""
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.ragas.entities import EvaluationResult, EvaluationRun
from src.domain.ragas.interfaces import EvaluationRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.ragas.models import (
    EvaluationResultModel,
    EvaluationRunModel,
    TestsetModel,
)


class EvaluationRepository(EvaluationRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save_run(self, run: EvaluationRun, request_id: str) -> EvaluationRun:
        self._logger.info("EvaluationRun save", request_id=request_id, run_id=run.id)
        model = EvaluationRunModel(
            id=run.id,
            eval_type=run.eval_type,
            target_type=run.target_type,
            target_id=run.target_id,
            status=run.status,
            total_cases=run.total_cases,
            config=run.config,
            error_message=run.error_message,
            created_at=run.created_at,
            completed_at=run.completed_at,
        )
        self._session.add(model)
        await self._session.flush()
        return run

    async def update_run(self, run: EvaluationRun, request_id: str) -> None:
        self._logger.info(
            "EvaluationRun update",
            request_id=request_id,
            run_id=run.id,
            status=run.status,
        )
        stmt = select(EvaluationRunModel).where(EvaluationRunModel.id == run.id)
        result = await self._session.execute(stmt)
        model = result.scalar_one()
        model.status = run.status
        model.completed_at = run.completed_at
        model.error_message = run.error_message
        model.total_cases = run.total_cases
        await self._session.flush()

    async def get_run(self, run_id: str, request_id: str) -> EvaluationRun | None:
        stmt = select(EvaluationRunModel).where(EvaluationRunModel.id == run_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return self._to_run_entity(model)

    async def list_runs(
        self,
        target_type: str | None,
        eval_type: str | None,
        limit: int,
        offset: int,
        request_id: str,
    ) -> tuple[list[EvaluationRun], int]:
        stmt = select(EvaluationRunModel)
        count_stmt = select(func.count(EvaluationRunModel.id))

        if target_type:
            stmt = stmt.where(EvaluationRunModel.target_type == target_type)
            count_stmt = count_stmt.where(
                EvaluationRunModel.target_type == target_type
            )
        if eval_type:
            stmt = stmt.where(EvaluationRunModel.eval_type == eval_type)
            count_stmt = count_stmt.where(
                EvaluationRunModel.eval_type == eval_type
            )

        stmt = stmt.order_by(EvaluationRunModel.created_at.desc())
        stmt = stmt.offset(offset).limit(limit)

        result = await self._session.execute(stmt)
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar() or 0

        return [self._to_run_entity(m) for m in result.scalars()], total

    async def delete_run(self, run_id: str, request_id: str) -> bool:
        self._logger.info("EvaluationRun delete", request_id=request_id, run_id=run_id)
        stmt = delete(EvaluationRunModel).where(EvaluationRunModel.id == run_id)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount > 0

    async def save_result(self, result: EvaluationResult, request_id: str) -> None:
        model = self._to_result_model(result)
        self._session.add(model)
        await self._session.flush()

    async def save_results_bulk(
        self, results: list[EvaluationResult], request_id: str
    ) -> None:
        self._logger.info(
            "EvaluationResult bulk save",
            request_id=request_id,
            count=len(results),
        )
        models = [self._to_result_model(r) for r in results]
        self._session.add_all(models)
        await self._session.flush()

    async def get_results_by_run(
        self, run_id: str, limit: int, offset: int, request_id: str
    ) -> tuple[list[EvaluationResult], int]:
        stmt = (
            select(EvaluationResultModel)
            .where(EvaluationResultModel.run_id == run_id)
            .order_by(EvaluationResultModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        count_stmt = (
            select(func.count(EvaluationResultModel.id))
            .where(EvaluationResultModel.run_id == run_id)
        )

        result = await self._session.execute(stmt)
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar() or 0

        return [self._to_result_entity(m) for m in result.scalars()], total

    async def get_run_summary(
        self, run_id: str, request_id: str
    ) -> dict[str, float]:
        stmt = (
            select(EvaluationResultModel.metrics)
            .where(EvaluationResultModel.run_id == run_id)
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            return {}

        totals: dict[str, float] = {}
        counts: dict[str, int] = {}
        for metrics in rows:
            if not metrics:
                continue
            for key, value in metrics.items():
                if isinstance(value, (int, float)):
                    totals[key] = totals.get(key, 0.0) + value
                    counts[key] = counts.get(key, 0) + 1

        return {
            key: totals[key] / counts[key]
            for key in totals
            if counts[key] > 0
        }

    async def save_testset(self, testset: dict, request_id: str) -> None:
        self._logger.info(
            "Testset save", request_id=request_id, testset_id=testset["id"]
        )
        model = TestsetModel(
            id=testset["id"],
            name=testset["name"],
            description=testset.get("description"),
            cases=testset["cases"],
            case_count=testset["case_count"],
            created_at=testset["created_at"],
        )
        self._session.add(model)
        await self._session.flush()

    async def list_testsets(
        self, limit: int, offset: int, request_id: str
    ) -> tuple[list[dict], int]:
        stmt = (
            select(TestsetModel)
            .order_by(TestsetModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        count_stmt = select(func.count(TestsetModel.id))

        result = await self._session.execute(stmt)
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar() or 0

        items = [
            {
                "id": m.id,
                "name": m.name,
                "description": m.description,
                "cases": m.cases,
                "case_count": m.case_count,
                "created_at": m.created_at,
            }
            for m in result.scalars()
        ]
        return items, total

    async def get_testset(self, testset_id: str, request_id: str) -> dict | None:
        stmt = select(TestsetModel).where(TestsetModel.id == testset_id)
        result = await self._session.execute(stmt)
        m = result.scalar_one_or_none()
        if m is None:
            return None
        return {
            "id": m.id,
            "name": m.name,
            "description": m.description,
            "cases": m.cases,
            "case_count": m.case_count,
            "created_at": m.created_at,
        }

    async def delete_testset(self, testset_id: str, request_id: str) -> bool:
        self._logger.info(
            "Testset delete", request_id=request_id, testset_id=testset_id
        )
        stmt = delete(TestsetModel).where(TestsetModel.id == testset_id)
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount > 0

    async def get_dashboard_stats(
        self, recent_limit: int, request_id: str
    ) -> dict:
        self._logger.info(
            "Dashboard stats query", request_id=request_id,
        )
        total_stmt = select(func.count(EvaluationRunModel.id))
        total = (await self._session.execute(total_stmt)).scalar() or 0

        status_stmt = (
            select(
                EvaluationRunModel.status,
                func.count(EvaluationRunModel.id),
            )
            .group_by(EvaluationRunModel.status)
        )
        status_rows = (await self._session.execute(status_stmt)).all()
        status_counts = {row[0]: row[1] for row in status_rows}

        tt_stmt = (
            select(
                EvaluationRunModel.target_type,
                func.count(EvaluationRunModel.id),
            )
            .group_by(EvaluationRunModel.target_type)
        )
        tt_rows = (await self._session.execute(tt_stmt)).all()
        target_type_counts = {row[0]: row[1] for row in tt_rows}

        completed_ids_stmt = (
            select(EvaluationRunModel.id)
            .where(EvaluationRunModel.status == "completed")
        )
        metrics_stmt = (
            select(EvaluationResultModel.metrics)
            .where(EvaluationResultModel.run_id.in_(completed_ids_stmt))
        )
        metrics_rows = (
            await self._session.execute(metrics_stmt)
        ).scalars().all()
        avg_metrics = self._calculate_avg_metrics(metrics_rows)

        recent_stmt = (
            select(EvaluationRunModel)
            .order_by(EvaluationRunModel.created_at.desc())
            .limit(recent_limit)
        )
        recent_result = await self._session.execute(recent_stmt)
        recent_runs = [
            self._to_run_entity(m) for m in recent_result.scalars()
        ]

        return {
            "total_runs": total,
            "status_counts": status_counts,
            "target_type_counts": target_type_counts,
            "avg_metrics": avg_metrics,
            "recent_runs": recent_runs,
        }

    async def list_runs_with_summary(
        self,
        target_type: str | None,
        eval_type: str | None,
        status: str | None,
        limit: int,
        offset: int,
        request_id: str,
    ) -> tuple[list[dict], int]:
        stmt = select(EvaluationRunModel)
        count_stmt = select(func.count(EvaluationRunModel.id))

        for col, val in [
            (EvaluationRunModel.target_type, target_type),
            (EvaluationRunModel.eval_type, eval_type),
            (EvaluationRunModel.status, status),
        ]:
            if val:
                stmt = stmt.where(col == val)
                count_stmt = count_stmt.where(col == val)

        stmt = (
            stmt.order_by(EvaluationRunModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await self._session.execute(stmt)
        total = (await self._session.execute(count_stmt)).scalar() or 0

        items = []
        for model in result.scalars():
            summary = await self.get_run_summary(model.id, request_id)
            items.append({
                "id": model.id,
                "eval_type": model.eval_type,
                "target_type": model.target_type,
                "status": model.status,
                "total_cases": model.total_cases,
                "created_at": model.created_at,
                "completed_at": model.completed_at,
                "summary": summary,
            })
        return items, total

    @staticmethod
    def _calculate_avg_metrics(metrics_rows: list) -> dict[str, float]:
        totals: dict[str, float] = {}
        counts: dict[str, int] = {}
        for metrics in metrics_rows:
            if not metrics:
                continue
            for key, value in metrics.items():
                if isinstance(value, (int, float)):
                    totals[key] = totals.get(key, 0.0) + value
                    counts[key] = counts.get(key, 0) + 1
        return {k: totals[k] / counts[k] for k in totals if counts[k] > 0}

    @staticmethod
    def _to_run_entity(model: EvaluationRunModel) -> EvaluationRun:
        return EvaluationRun(
            id=model.id,
            eval_type=model.eval_type,
            target_type=model.target_type,
            target_id=model.target_id,
            status=model.status,
            total_cases=model.total_cases,
            config=model.config or {},
            error_message=model.error_message,
            created_at=model.created_at,
            completed_at=model.completed_at,
        )

    @staticmethod
    def _to_result_entity(model: EvaluationResultModel) -> EvaluationResult:
        return EvaluationResult(
            id=model.id,
            run_id=model.run_id,
            question=model.question,
            ground_truth=model.ground_truth,
            answer=model.answer,
            contexts=model.contexts or [],
            metrics=model.metrics or {},
            created_at=model.created_at,
        )

    @staticmethod
    def _to_result_model(result: EvaluationResult) -> EvaluationResultModel:
        return EvaluationResultModel(
            id=result.id,
            run_id=result.run_id,
            question=result.question,
            ground_truth=result.ground_truth,
            answer=result.answer,
            contexts=result.contexts,
            metrics=result.metrics,
            created_at=result.created_at,
        )
