"""SQLAlchemy implementation of LlmCallRepositoryInterface.

AGENT-OBS-001 §4-2: ai_llm_call 영속화 + 사용자별/LLM별 집계 쿼리.
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent_run.entities import LlmCall
from src.domain.agent_run.interfaces import (
    LlmCallRepositoryInterface,
    LlmUsageRow,
    NodeUsageRow,
    UsageSummaryRow,
    UsageTimeseriesPoint,
    UserUsageRow,
)
from src.domain.agent_run.value_objects import (
    CostUsd,
    RunId,
    RunPurpose,
    TokenUsage,
)
from src.infrastructure.persistence.models.agent_run import (
    AgentRunModel,
    AgentRunStepModel,
    LlmCallModel,
)


class SqlAlchemyLlmCallRepository(LlmCallRepositoryInterface):
    """MySQL 구현. 집계 쿼리는 단일 테이블 스캔(비정규화 인덱스 활용)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, call: LlmCall) -> LlmCall:
        row = LlmCallModel(
            id=call.id,
            run_id=call.run_id.value,
            step_id=call.step_id,
            tool_call_id=call.tool_call_id,
            user_id=call.user_id,
            agent_id=call.agent_id,
            llm_model_id=call.llm_model_id,
            provider=call.provider,
            model_name=call.model_name,
            purpose=call.purpose.value if call.purpose else None,
            prompt_tokens=call.token_usage.prompt_tokens,
            completion_tokens=call.token_usage.completion_tokens,
            total_tokens=call.token_usage.total_tokens,
            input_price_per_1k_usd=call.input_price_per_1k_usd,
            output_price_per_1k_usd=call.output_price_per_1k_usd,
            input_cost_usd=call.cost_usd.input_usd,
            output_cost_usd=call.cost_usd.output_usd,
            total_cost_usd=call.cost_usd.total_usd,
            latency_ms=call.latency_ms,
            status=call.status,
            error_text=call.error_text,
            created_at=call.created_at,
        )
        self._session.add(row)
        await self._session.flush()
        return call

    async def find_by_run(self, run_id: RunId) -> List[LlmCall]:
        stmt = (
            select(LlmCallModel)
            .where(LlmCallModel.run_id == run_id.value)
            .order_by(LlmCallModel.created_at)
        )
        result = await self._session.execute(stmt)
        return [self._to_domain(r) for r in result.scalars().all()]

    async def aggregate_by_user(
        self, from_dt: datetime, to_dt: datetime
    ) -> List[UserUsageRow]:
        stmt = (
            select(
                LlmCallModel.user_id.label("user_id"),
                func.coalesce(func.sum(LlmCallModel.total_tokens), 0).label("tokens"),
                func.coalesce(func.sum(LlmCallModel.total_cost_usd), 0).label("cost"),
                func.count().label("calls"),
            )
            .where(LlmCallModel.created_at.between(from_dt, to_dt))
            .group_by(LlmCallModel.user_id)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            UserUsageRow(
                user_id=r.user_id,
                total_tokens=int(r.tokens),
                total_cost_usd=Decimal(r.cost),
                call_count=int(r.calls),
            )
            for r in rows
        ]

    async def aggregate_by_llm_model(
        self, from_dt: datetime, to_dt: datetime
    ) -> List[LlmUsageRow]:
        stmt = (
            select(
                LlmCallModel.llm_model_id.label("model_id"),
                LlmCallModel.provider.label("provider"),
                LlmCallModel.model_name.label("model_name"),
                func.coalesce(func.sum(LlmCallModel.total_tokens), 0).label("tokens"),
                func.coalesce(func.sum(LlmCallModel.total_cost_usd), 0).label("cost"),
                func.count().label("calls"),
            )
            .where(LlmCallModel.created_at.between(from_dt, to_dt))
            .group_by(
                LlmCallModel.llm_model_id,
                LlmCallModel.provider,
                LlmCallModel.model_name,
            )
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            LlmUsageRow(
                llm_model_id=r.model_id,
                provider=r.provider,
                model_name=r.model_name,
                total_tokens=int(r.tokens),
                total_cost_usd=Decimal(r.cost),
                call_count=int(r.calls),
            )
            for r in rows
        ]

    async def aggregate_user_x_llm(
        self, user_id: str, from_dt: datetime, to_dt: datetime
    ) -> List[LlmUsageRow]:
        stmt = (
            select(
                LlmCallModel.llm_model_id.label("model_id"),
                LlmCallModel.provider.label("provider"),
                LlmCallModel.model_name.label("model_name"),
                func.coalesce(func.sum(LlmCallModel.total_tokens), 0).label("tokens"),
                func.coalesce(func.sum(LlmCallModel.total_cost_usd), 0).label("cost"),
                func.count().label("calls"),
            )
            .where(
                LlmCallModel.user_id == user_id,
                LlmCallModel.created_at.between(from_dt, to_dt),
            )
            .group_by(
                LlmCallModel.llm_model_id,
                LlmCallModel.provider,
                LlmCallModel.model_name,
            )
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            LlmUsageRow(
                llm_model_id=r.model_id,
                provider=r.provider,
                model_name=r.model_name,
                total_tokens=int(r.tokens),
                total_cost_usd=Decimal(r.cost),
                call_count=int(r.calls),
            )
            for r in rows
        ]

    async def aggregate_by_node(
        self, from_dt: datetime, to_dt: datetime
    ) -> List[NodeUsageRow]:
        """노드별 토큰/비용 GROUP BY — INNER JOIN ai_run_step.

        M4: step_id IS NULL인 행은 INNER JOIN으로 자연 제외.
        """
        stmt = (
            select(
                AgentRunStepModel.node_name.label("node_name"),
                func.coalesce(func.sum(LlmCallModel.total_tokens), 0).label("tokens"),
                func.coalesce(func.sum(LlmCallModel.total_cost_usd), 0).label("cost"),
                func.count().label("calls"),
            )
            .join(
                AgentRunStepModel,
                AgentRunStepModel.id == LlmCallModel.step_id,
            )
            .where(LlmCallModel.created_at.between(from_dt, to_dt))
            .group_by(AgentRunStepModel.node_name)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            NodeUsageRow(
                node_name=r.node_name,
                call_count=int(r.calls),
                total_tokens=int(r.tokens),
                total_cost_usd=Decimal(r.cost),
            )
            for r in rows
        ]

    # ── M5: dashboard summary + timeseries ────────────────────────────
    async def aggregate_summary(
        self,
        from_dt: datetime,
        to_dt: datetime,
        user_id: Optional[str] = None,
    ) -> UsageSummaryRow:
        """카드 4종 단일 응답.

        tokens/cost는 ai_llm_call 합계, run 수·성공/실패는 ai_run 합계.
        user_id 주어지면 두 sub-query 모두 동일 user_id 필터 적용.
        """
        token_stmt = (
            select(
                func.coalesce(func.sum(LlmCallModel.total_tokens), 0).label("tokens"),
                func.coalesce(func.sum(LlmCallModel.total_cost_usd), 0).label("cost"),
            )
            .where(LlmCallModel.created_at.between(from_dt, to_dt))
        )
        if user_id is not None:
            token_stmt = token_stmt.where(LlmCallModel.user_id == user_id)

        run_stmt = (
            select(
                func.count().label("total_runs"),
                func.coalesce(
                    func.sum(case((AgentRunModel.status == "SUCCESS", 1), else_=0)),
                    0,
                ).label("success_runs"),
                func.coalesce(
                    func.sum(case((AgentRunModel.status == "FAILED", 1), else_=0)),
                    0,
                ).label("failed_runs"),
            )
            .where(AgentRunModel.started_at.between(from_dt, to_dt))
        )
        if user_id is not None:
            run_stmt = run_stmt.where(AgentRunModel.user_id == user_id)

        token_row = (await self._session.execute(token_stmt)).one()
        run_row = (await self._session.execute(run_stmt)).one()
        return UsageSummaryRow(
            from_dt=from_dt,
            to_dt=to_dt,
            total_runs=int(run_row.total_runs),
            success_runs=int(run_row.success_runs),
            failed_runs=int(run_row.failed_runs),
            total_tokens=int(token_row.tokens),
            total_cost_usd=Decimal(token_row.cost),
        )

    async def aggregate_timeseries(
        self,
        from_dt: datetime,
        to_dt: datetime,
        user_id: Optional[str] = None,
    ) -> List[UsageTimeseriesPoint]:
        """일자별 bucket — ai_run LEFT JOIN ai_llm_call GROUP BY DATE(started_at)."""
        bucket = cast(AgentRunModel.started_at, Date).label("bucket")
        stmt = (
            select(
                bucket,
                func.count(func.distinct(AgentRunModel.id)).label("run_count"),
                func.coalesce(func.sum(LlmCallModel.total_tokens), 0).label("tokens"),
                func.coalesce(func.sum(LlmCallModel.total_cost_usd), 0).label("cost"),
            )
            .select_from(AgentRunModel)
            .outerjoin(
                LlmCallModel,
                LlmCallModel.run_id == AgentRunModel.id,
            )
            .where(AgentRunModel.started_at.between(from_dt, to_dt))
            .group_by(bucket)
            .order_by(bucket.asc())
        )
        if user_id is not None:
            stmt = stmt.where(AgentRunModel.user_id == user_id)

        rows = (await self._session.execute(stmt)).all()
        return [
            UsageTimeseriesPoint(
                bucket=r.bucket,
                run_count=int(r.run_count),
                total_tokens=int(r.tokens),
                total_cost_usd=Decimal(r.cost),
            )
            for r in rows
        ]

    def _to_domain(self, row: LlmCallModel) -> LlmCall:
        return LlmCall(
            id=row.id,
            run_id=RunId(row.run_id),
            step_id=row.step_id,
            tool_call_id=row.tool_call_id,
            user_id=row.user_id,
            agent_id=row.agent_id,
            llm_model_id=row.llm_model_id,
            provider=row.provider,
            model_name=row.model_name,
            purpose=RunPurpose(row.purpose) if row.purpose else None,
            token_usage=TokenUsage(
                prompt_tokens=row.prompt_tokens,
                completion_tokens=row.completion_tokens,
                total_tokens=row.total_tokens,
            ),
            input_price_per_1k_usd=row.input_price_per_1k_usd,
            output_price_per_1k_usd=row.output_price_per_1k_usd,
            cost_usd=CostUsd(
                input_usd=row.input_cost_usd,
                output_usd=row.output_cost_usd,
                total_usd=row.total_cost_usd,
            ),
            latency_ms=row.latency_ms,
            status=row.status,
            error_text=row.error_text,
            created_at=row.created_at,
        )
