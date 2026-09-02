"""모델 스윕 MySQL 저장소.

Design Ref: §9.1 / §4.2 — 스윕 CRUD + 모델별 4축 집계.
집계는 evaluation_run ⋈ evaluation_result ⋈ ai_run 으로 이뤄지며,
ai_run 조인 실패(관측 선삭제 등)는 비용·지연만 N/A로 낙하시킨다 (D11).
Repository 내부에서 commit/rollback을 호출하지 않는다 (docs/rules/db-session.md).
"""
import statistics
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.eval_sweep.entity import EvaluationSweep, SweepRow
from src.domain.eval_sweep.interfaces import SweepRepositoryInterface
from src.domain.eval_sweep.policies import mean_ignoring_none
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.eval_sweep.models import EvaluationSweepModel
from src.infrastructure.persistence.models.agent_run import AgentRunModel
from src.infrastructure.ragas.models import EvaluationResultModel, EvaluationRunModel

# 도구 지표 중 대표값으로 매트릭스에 노출할 키 (§3.5).
_TOOL_F1_KEY = "tool_f1"


class SweepRepository(SweepRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def save(self, sweep: EvaluationSweep, request_id: str) -> EvaluationSweep:
        self._logger.info(
            "EvaluationSweep save", request_id=request_id, sweep_id=sweep.id
        )
        self._session.add(_to_model(sweep))
        await self._session.flush()
        return sweep

    async def update(self, sweep: EvaluationSweep, request_id: str) -> None:
        model = await self._session.get(EvaluationSweepModel, sweep.id)
        if model is None:
            self._logger.warning(
                "EvaluationSweep update skipped — not found",
                request_id=request_id,
                sweep_id=sweep.id,
            )
            return
        model.status = sweep.status
        model.completed_runs = sweep.completed_runs
        model.error_message = sweep.error_message
        model.completed_at = sweep.completed_at
        await self._session.flush()

    async def get(self, sweep_id: str, request_id: str) -> EvaluationSweep | None:
        model = await self._session.get(EvaluationSweepModel, sweep_id)
        return _to_entity(model) if model is not None else None

    async def list_by_user(
        self, user_id: str | None, limit: int, offset: int, request_id: str
    ) -> tuple[list[EvaluationSweep], int]:
        stmt = select(EvaluationSweepModel)
        count_stmt = select(func.count(EvaluationSweepModel.id))
        # user_id=None은 관리자 — 필터를 걸지 않는다 (ragas_router._scope 선례).
        if user_id is not None:
            stmt = stmt.where(EvaluationSweepModel.user_id == user_id)
            count_stmt = count_stmt.where(EvaluationSweepModel.user_id == user_id)

        stmt = stmt.order_by(EvaluationSweepModel.created_at.desc())
        stmt = stmt.offset(offset).limit(limit)

        rows = await self._session.execute(stmt)
        total = (await self._session.execute(count_stmt)).scalar() or 0
        return [_to_entity(m) for m in rows.scalars()], total

    async def delete(self, sweep_id: str, request_id: str) -> bool:
        model = await self._session.get(EvaluationSweepModel, sweep_id)
        if model is None:
            return False
        # 하위 evaluation_run은 DDL의 FK CASCADE가 정리한다 (V068).
        await self._session.delete(model)
        await self._session.flush()
        return True

    async def get_rows(self, sweep_id: str, request_id: str) -> list[SweepRow]:
        """모델별 4축 집계 (§4.2 rows[])."""
        runs = (
            await self._session.execute(
                select(EvaluationRunModel)
                .where(EvaluationRunModel.sweep_id == sweep_id)
                .order_by(EvaluationRunModel.created_at.asc())
            )
        ).scalars().all()

        return [await self._build_row(run, request_id) for run in runs]

    # ── 집계 ────────────────────────────────────────────────────────

    async def _build_row(self, run: EvaluationRunModel, request_id: str) -> SweepRow:
        results = (
            await self._session.execute(
                select(EvaluationResultModel).where(
                    EvaluationResultModel.run_id == run.id
                )
            )
        ).scalars().all()

        observed = await self._observability_of(results)
        return SweepRow(
            run_id=run.id,
            llm_model_id=run.llm_model_id,
            status=run.status,
            quality=_quality_of(results),
            cost_usd=observed["cost_usd"],
            latency_p50_ms=observed["p50"],
            latency_p95_ms=observed["p95"],
            tool_f1=mean_ignoring_none(
                [(r.metrics or {}).get(_TOOL_F1_KEY) for r in results]
            ),
            measured_cases=len(results),
            failed_cases=max(run.total_cases - len(results), 0),
            error_message=run.error_message,
        )

    async def _observability_of(self, results: list) -> dict:
        """ai_run 조인으로 비용·지연을 회수한다 (D10).

        조인 대상이 없으면(관측 미생성·선삭제) 전부 None — 품질·도구 지표는 살린다.
        """
        run_ids = [r.ai_run_id for r in results if r.ai_run_id]
        if not run_ids:
            return {"cost_usd": None, "p50": None, "p95": None}

        rows = (
            await self._session.execute(
                select(
                    AgentRunModel.total_cost_usd, AgentRunModel.latency_ms
                ).where(AgentRunModel.id.in_(run_ids))
            )
        ).all()
        if not rows:
            return {"cost_usd": None, "p50": None, "p95": None}

        costs = [r[0] for r in rows if r[0] is not None]
        latencies = sorted(r[1] for r in rows if r[1] is not None)
        return {
            "cost_usd": sum(costs, Decimal("0")) if costs else None,
            "p50": _percentile(latencies, 50),
            "p95": _percentile(latencies, 95),
        }


def _quality_of(results: list) -> dict[str, float | None]:
    """RAGAS 지표별 평균. None(N/A)은 분모에서 제외한다 (§3.5)."""
    keys: set[str] = set()
    for r in results:
        keys.update(k for k in (r.metrics or {}) if not k.startswith("tool_"))
    return {
        key: mean_ignoring_none([(r.metrics or {}).get(key) for r in results])
        for key in sorted(keys)
    }


def _percentile(sorted_values: list[int], pct: int) -> int | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    return int(statistics.quantiles(sorted_values, n=100)[pct - 1])


def _to_model(sweep: EvaluationSweep) -> EvaluationSweepModel:
    return EvaluationSweepModel(
        id=sweep.id,
        name=sweep.name,
        agent_id=sweep.agent_id,
        testset_id=sweep.testset_id,
        judge_llm_model_id=sweep.judge_llm_model_id,
        model_ids=sweep.model_ids,
        metrics=sweep.metrics,
        temperature=Decimal(str(sweep.temperature)),
        status=sweep.status,
        total_runs=sweep.total_runs,
        completed_runs=sweep.completed_runs,
        estimated_cost_usd=sweep.estimated_cost_usd,
        user_id=sweep.user_id,
        error_message=sweep.error_message,
        created_at=sweep.created_at,
        completed_at=sweep.completed_at,
    )


def _to_entity(model: EvaluationSweepModel) -> EvaluationSweep:
    return EvaluationSweep(
        id=model.id,
        name=model.name,
        agent_id=model.agent_id,
        testset_id=model.testset_id,
        judge_llm_model_id=model.judge_llm_model_id,
        model_ids=list(model.model_ids or []),
        metrics=list(model.metrics or []),
        temperature=float(model.temperature or 0),
        status=model.status,
        total_runs=model.total_runs,
        completed_runs=model.completed_runs,
        estimated_cost_usd=model.estimated_cost_usd,
        user_id=model.user_id,
        error_message=model.error_message,
        created_at=model.created_at,
        completed_at=model.completed_at,
    )
