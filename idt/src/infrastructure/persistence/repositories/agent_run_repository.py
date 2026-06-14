"""SQLAlchemy implementation of AgentRunRepositoryInterface.

AGENT-OBS-001 §4: ai_run / ai_run_step / ai_tool_call / ai_retrieval_source 영속화.
DB-001 §10.3 — Repository는 commit/rollback 호출 금지 (Tracker가 세션 단위 관리).
"""
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent_run.entities import (
    AgentRun,
    AgentRunStep,
    RetrievalSource,
    ToolCall,
)
from src.domain.agent_run.interfaces import (
    AgentRunRepositoryInterface,
    RunListFilters,
)
from src.domain.agent_run.value_objects import (
    CostUsd,
    NodeType,
    RunId,
    RunStatus,
    StepStatus,
    TokenUsage,
)
from src.infrastructure.persistence.models.agent_run import (
    AgentRunModel,
    AgentRunStepModel,
    RetrievalSourceModel,
    ToolCallModel,
)


def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """MySQL DATETIME에서 fetch된 naive datetime을 UTC aware로 정규화.

    저장 정책: 본 시스템은 모든 시각을 UTC로 저장한다 (tracker._utcnow()).
    MySQL DATETIME은 tzinfo를 보존하지 않으므로, fetch 시점에 UTC tzinfo를 부여한다.
    이미 aware인 경우(테스트에서 직접 주입 등)는 변환하지 않고 그대로 반환한다.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class SqlAlchemyAgentRunRepository(AgentRunRepositoryInterface):
    """MySQL 구현. session.commit은 호출자가 담당."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── ai_run ────────────────────────────────────────────────────────
    async def save_run(self, run: AgentRun) -> AgentRun:
        row = self._run_to_orm(run)
        self._session.add(row)
        await self._session.flush()
        return run

    async def update_run(self, run: AgentRun) -> None:
        stmt = select(AgentRunModel).where(AgentRunModel.id == run.id.value)
        result = await self._session.execute(stmt)
        row = result.scalar_one()
        row.user_message_id = run.user_message_id
        row.langsmith_trace_id = run.langsmith_trace_id
        row.langsmith_run_url = run.langsmith_run_url
        row.status = run.status.value
        row.prompt_tokens = run.token_usage.prompt_tokens
        row.completion_tokens = run.token_usage.completion_tokens
        row.total_tokens = run.token_usage.total_tokens
        row.total_cost_usd = run.cost_usd.total_usd
        row.llm_call_count = run.llm_call_count
        row.ended_at = run.ended_at
        row.latency_ms = run.latency_ms
        row.error_message = run.error_message
        row.error_stack = run.error_stack
        await self._session.flush()

    async def find_run(self, run_id: RunId) -> Optional[AgentRun]:
        stmt = select(AgentRunModel).where(AgentRunModel.id == run_id.value)
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._run_to_domain(row) if row else None

    async def apply_completion_totals(
        self,
        run_id: RunId,
        langsmith_trace_id: Optional[str],
        langsmith_run_url: Optional[str],
    ) -> None:
        """Design §14-5: 단일 SQL로 SUM(ai_llm_call.*) → ai_run.* UPDATE.

        TIMESTAMPDIFF(MICROSECOND, started_at, NOW()) / 1000 으로 latency_ms 계산.
        status='SUCCESS' 전환. 동일 run에 대한 idempotent 보호를 위해 status='RUNNING' 조건.
        """
        await self._session.execute(
            text(
                """
                UPDATE ai_run SET
                    prompt_tokens = COALESCE(
                        (SELECT SUM(prompt_tokens) FROM ai_llm_call WHERE run_id = :rid), 0
                    ),
                    completion_tokens = COALESCE(
                        (SELECT SUM(completion_tokens) FROM ai_llm_call WHERE run_id = :rid), 0
                    ),
                    total_tokens = COALESCE(
                        (SELECT SUM(total_tokens) FROM ai_llm_call WHERE run_id = :rid), 0
                    ),
                    total_cost_usd = COALESCE(
                        (SELECT SUM(total_cost_usd) FROM ai_llm_call WHERE run_id = :rid), 0
                    ),
                    llm_call_count = (
                        SELECT COUNT(*) FROM ai_llm_call WHERE run_id = :rid
                    ),
                    status = 'SUCCESS',
                    ended_at = NOW(),
                    langsmith_trace_id = :trace_id,
                    langsmith_run_url = :run_url,
                    latency_ms = TIMESTAMPDIFF(MICROSECOND, started_at, NOW()) / 1000
                WHERE id = :rid AND status = 'RUNNING'
                """
            ),
            {
                "rid": run_id.value,
                "trace_id": langsmith_trace_id,
                "run_url": langsmith_run_url,
            },
        )
        await self._session.flush()

    async def mark_failed(
        self,
        run_id: RunId,
        error_message: Optional[str],
        error_stack: Optional[str],
    ) -> None:
        stmt = (
            update(AgentRunModel)
            .where(
                AgentRunModel.id == run_id.value,
                AgentRunModel.status == RunStatus.RUNNING.value,
            )
            .values(
                status=RunStatus.FAILED.value,
                ended_at=datetime.now(timezone.utc),
                error_message=error_message,
                error_stack=error_stack,
            )
        )
        await self._session.execute(stmt)
        await self._session.flush()

    # ── ai_run_step ───────────────────────────────────────────────────
    async def save_step(self, step: AgentRunStep) -> AgentRunStep:
        row = AgentRunStepModel(
            id=step.id,
            run_id=step.run_id.value,
            step_index=step.step_index,
            node_name=step.node_name,
            node_type=step.node_type.value,
            llm_model_id=step.llm_model_id,
            status=step.status.value,
            input_summary=step.input_summary,
            output_summary=step.output_summary,
            started_at=step.started_at,
            ended_at=step.ended_at,
            latency_ms=step.latency_ms,
            error_text=step.error_text,
        )
        self._session.add(row)
        await self._session.flush()
        return step

    async def update_step(self, step: AgentRunStep) -> None:
        stmt = select(AgentRunStepModel).where(AgentRunStepModel.id == step.id)
        result = await self._session.execute(stmt)
        row = result.scalar_one()
        row.status = step.status.value
        row.output_summary = step.output_summary
        row.ended_at = step.ended_at
        row.latency_ms = step.latency_ms
        row.error_text = step.error_text
        await self._session.flush()

    async def find_steps(self, run_id: RunId) -> List[AgentRunStep]:
        stmt = (
            select(AgentRunStepModel)
            .where(AgentRunStepModel.run_id == run_id.value)
            .order_by(AgentRunStepModel.step_index)
        )
        result = await self._session.execute(stmt)
        return [self._step_to_domain(r) for r in result.scalars().all()]

    # ── ai_tool_call ──────────────────────────────────────────────────
    async def save_tool_call(self, call: ToolCall) -> ToolCall:
        row = self._tool_to_orm(call)
        self._session.add(row)
        await self._session.flush()
        return call

    async def update_tool_call(self, call: ToolCall) -> None:
        stmt = select(ToolCallModel).where(ToolCallModel.id == call.id)
        result = await self._session.execute(stmt)
        row = result.scalar_one()
        row.result_summary = call.result_summary
        row.result_json = call.result_json
        row.prompt_tokens = (
            call.token_usage.prompt_tokens if call.token_usage else None
        )
        row.completion_tokens = (
            call.token_usage.completion_tokens if call.token_usage else None
        )
        row.total_tokens = (
            call.token_usage.total_tokens if call.token_usage else None
        )
        row.total_cost_usd = call.total_cost_usd
        row.latency_ms = call.latency_ms
        row.status = call.status
        row.error_text = call.error_text
        row.llm_model_id = call.llm_model_id
        await self._session.flush()

    async def find_tool_calls(self, run_id: RunId) -> List[ToolCall]:
        stmt = (
            select(ToolCallModel)
            .where(ToolCallModel.run_id == run_id.value)
            .order_by(ToolCallModel.created_at)
        )
        result = await self._session.execute(stmt)
        return [self._tool_to_domain(r) for r in result.scalars().all()]

    # ── ai_retrieval_source ───────────────────────────────────────────
    async def save_retrieval(self, source: RetrievalSource) -> RetrievalSource:
        row = RetrievalSourceModel(
            id=source.id,
            run_id=source.run_id.value,
            tool_call_id=source.tool_call_id,
            collection_name=source.collection_name,
            document_id=source.document_id,
            chunk_id=source.chunk_id,
            score=source.score,
            rank_index=source.rank_index,
            content_preview=source.content_preview,
            metadata_json=source.metadata_json,
            created_at=source.created_at,
        )
        self._session.add(row)
        await self._session.flush()
        return source

    async def find_retrievals(self, run_id: RunId) -> List[RetrievalSource]:
        stmt = (
            select(RetrievalSourceModel)
            .where(RetrievalSourceModel.run_id == run_id.value)
            .order_by(RetrievalSourceModel.rank_index)
        )
        result = await self._session.execute(stmt)
        return [self._retrieval_to_domain(r) for r in result.scalars().all()]

    # ── M5: admin run list + count ────────────────────────────────────
    async def list_runs(self, filters: RunListFilters) -> List[AgentRun]:
        stmt = select(AgentRunModel)
        stmt = self._apply_run_filters(stmt, filters)
        stmt = stmt.order_by(AgentRunModel.started_at.desc())
        stmt = stmt.limit(filters.limit).offset(filters.offset)
        result = await self._session.execute(stmt)
        return [self._run_to_domain(r) for r in result.scalars().all()]

    async def count_runs(self, filters: RunListFilters) -> int:
        stmt = select(func.count()).select_from(AgentRunModel)
        stmt = self._apply_run_filters(stmt, filters)
        return int((await self._session.execute(stmt)).scalar_one())

    def _apply_run_filters(self, stmt, filters: RunListFilters):
        """M5: list_runs / count_runs 공통 WHERE 절 빌더."""
        if filters.from_dt is not None:
            stmt = stmt.where(AgentRunModel.started_at >= filters.from_dt)
        if filters.to_dt is not None:
            stmt = stmt.where(AgentRunModel.started_at < filters.to_dt)
        if filters.user_id is not None:
            stmt = stmt.where(AgentRunModel.user_id == filters.user_id)
        if filters.agent_id is not None:
            stmt = stmt.where(AgentRunModel.agent_id == filters.agent_id)
        if filters.status is not None:
            stmt = stmt.where(AgentRunModel.status == filters.status)
        return stmt

    # ── mappers ───────────────────────────────────────────────────────
    def _run_to_orm(self, run: AgentRun) -> AgentRunModel:
        return AgentRunModel(
            id=run.id.value,
            conversation_id=run.conversation_id,
            user_id=run.user_id,
            agent_id=run.agent_id,
            llm_model_id=run.llm_model_id,
            user_message_id=run.user_message_id,
            status=run.status.value,
            langgraph_thread_id=run.langgraph_thread_id,
            langsmith_trace_id=run.langsmith_trace_id,
            langsmith_run_url=run.langsmith_run_url,
            prompt_tokens=run.token_usage.prompt_tokens,
            completion_tokens=run.token_usage.completion_tokens,
            total_tokens=run.token_usage.total_tokens,
            total_cost_usd=run.cost_usd.total_usd,
            llm_call_count=run.llm_call_count,
            started_at=run.started_at,
            ended_at=run.ended_at,
            latency_ms=run.latency_ms,
            error_message=run.error_message,
            error_stack=run.error_stack,
        )

    def _run_to_domain(self, row: AgentRunModel) -> AgentRun:
        return AgentRun(
            id=RunId(row.id),
            conversation_id=row.conversation_id,
            user_id=row.user_id,
            agent_id=row.agent_id,
            llm_model_id=row.llm_model_id,
            user_message_id=row.user_message_id,
            status=RunStatus(row.status),
            langgraph_thread_id=row.langgraph_thread_id,
            langsmith_trace_id=row.langsmith_trace_id,
            langsmith_run_url=row.langsmith_run_url,
            token_usage=TokenUsage(
                prompt_tokens=row.prompt_tokens,
                completion_tokens=row.completion_tokens,
                total_tokens=row.total_tokens,
            ),
            cost_usd=CostUsd(total_usd=row.total_cost_usd),
            llm_call_count=row.llm_call_count,
            started_at=_to_utc(row.started_at),
            ended_at=_to_utc(row.ended_at),
            latency_ms=row.latency_ms,
            error_message=row.error_message,
            error_stack=row.error_stack,
        )

    def _step_to_domain(self, row: AgentRunStepModel) -> AgentRunStep:
        return AgentRunStep(
            id=row.id,
            run_id=RunId(row.run_id),
            step_index=row.step_index,
            node_name=row.node_name,
            node_type=NodeType(row.node_type),
            llm_model_id=row.llm_model_id,
            status=StepStatus(row.status),
            input_summary=row.input_summary,
            output_summary=row.output_summary,
            started_at=_to_utc(row.started_at),
            ended_at=_to_utc(row.ended_at),
            latency_ms=row.latency_ms,
            error_text=row.error_text,
        )

    def _tool_to_orm(self, call: ToolCall) -> ToolCallModel:
        return ToolCallModel(
            id=call.id,
            run_id=call.run_id.value,
            step_id=call.step_id,
            tool_name=call.tool_name,
            llm_model_id=call.llm_model_id,
            arguments_json=call.arguments_json,
            result_summary=call.result_summary,
            result_json=call.result_json,
            prompt_tokens=(
                call.token_usage.prompt_tokens if call.token_usage else None
            ),
            completion_tokens=(
                call.token_usage.completion_tokens if call.token_usage else None
            ),
            total_tokens=(
                call.token_usage.total_tokens if call.token_usage else None
            ),
            total_cost_usd=call.total_cost_usd,
            latency_ms=call.latency_ms,
            status=call.status,
            error_text=call.error_text,
            created_at=call.created_at,
        )

    def _tool_to_domain(self, row: ToolCallModel) -> ToolCall:
        token_usage: Optional[TokenUsage] = None
        if row.total_tokens is not None:
            token_usage = TokenUsage(
                prompt_tokens=row.prompt_tokens or 0,
                completion_tokens=row.completion_tokens or 0,
                total_tokens=row.total_tokens or 0,
            )
        return ToolCall(
            id=row.id,
            run_id=RunId(row.run_id),
            step_id=row.step_id,
            tool_name=row.tool_name,
            llm_model_id=row.llm_model_id,
            arguments_json=row.arguments_json,
            result_summary=row.result_summary,
            result_json=row.result_json,
            token_usage=token_usage,
            total_cost_usd=row.total_cost_usd,
            latency_ms=row.latency_ms,
            status=row.status,
            error_text=row.error_text,
            created_at=_to_utc(row.created_at),
        )

    def _retrieval_to_domain(self, row: RetrievalSourceModel) -> RetrievalSource:
        return RetrievalSource(
            id=row.id,
            run_id=RunId(row.run_id),
            tool_call_id=row.tool_call_id,
            collection_name=row.collection_name,
            document_id=row.document_id,
            chunk_id=row.chunk_id,
            score=float(row.score) if row.score is not None else None,
            rank_index=row.rank_index,
            content_preview=row.content_preview,
            metadata_json=row.metadata_json,
            created_at=_to_utc(row.created_at),
        )
