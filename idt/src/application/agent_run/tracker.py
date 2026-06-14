"""RunTracker: AgentRun 라이프사이클 + best-effort 영속화.

AGENT-OBS-001 §3-1 / §4-3:
- start_run: ai_run INSERT (status=RUNNING) — 즉시 commit, 실패 시 RuntimeError
- complete_run: SUM(ai_llm_call.*) → ai_run UPDATE (status=SUCCESS) — best-effort
- fail_run: status=FAILED + error_message/stack
- record_step / record_tool_call / record_retrieval / record_llm_call: best-effort

세션 정책 (DB-001 §10.3 준수):
- 각 메서드가 session_factory에서 새 세션 + 트랜잭션을 열고 commit/rollback 책임진다.
- Repository는 commit 호출 금지 (flush까지만).
"""
import traceback
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from src.application.agent_run.cost_calculator import CostCalculator
from src.application.agent_run.model_name_resolver import ModelNameResolver
from src.domain.agent_run.entities import (
    AgentRun,
    AgentRunStep,
    LlmCall,
    RetrievalSource,
    ToolCall,
)
from src.domain.agent_run.policies import CostCalculationPolicy
from src.domain.agent_run.value_objects import (
    CostUsd,
    NodeType,
    RunId,
    RunPurpose,
    RunStatus,
    StepStatus,
    TokenUsage,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.persistence.repositories.agent_run_repository import (
    SqlAlchemyAgentRunRepository,
)
from src.infrastructure.persistence.repositories.llm_call_repository import (
    SqlAlchemyLlmCallRepository,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _compute_latency_ms(
    started_at: Optional[datetime],
    ended_at: Optional[datetime],
) -> Optional[int]:
    """두 datetime 간 latency(ms) 계산. naive datetime은 UTC로 보정.

    Mapper(_*_to_domain)에서 이미 aware UTC로 정규화하지만,
    mapper 우회 경로(직접 ORM, 테스트 mock)에서 naive가 들어와도
    TypeError가 발생하지 않도록 2차 방어선 역할을 한다.
    """
    if started_at is None or ended_at is None:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if ended_at.tzinfo is None:
        ended_at = ended_at.replace(tzinfo=timezone.utc)
    delta = ended_at - started_at
    return int(delta.total_seconds() * 1000)


class RunTracker:
    """관측성 라이프사이클 파사드. Repository는 메서드 내부에서 인스턴스화."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        cost_calculator: CostCalculator,
        model_name_resolver: ModelNameResolver,
        logger: LoggerInterface,
    ) -> None:
        self._session_factory = session_factory
        self._cost_calc = cost_calculator
        self._resolver = model_name_resolver
        self._logger = logger

    # ── start_run (immediate commit; raise on failure) ────────────────
    async def start_run(
        self,
        run_id: RunId,
        conversation_id: str,
        user_id: str,
        agent_id: str,
        agent_llm_model_id: Optional[str],
        user_message_id: Optional[int],
        langgraph_thread_id: str,
    ) -> RunId:
        """ai_run INSERT. 실패 시 RuntimeError raise (관측성 시작 자체가 깨진 상황)."""
        run = AgentRun(
            id=run_id,
            conversation_id=conversation_id,
            user_id=user_id,
            agent_id=agent_id,
            llm_model_id=agent_llm_model_id,
            user_message_id=user_message_id,
            status=RunStatus.RUNNING,
            langgraph_thread_id=langgraph_thread_id,
            langsmith_trace_id=None,
            langsmith_run_url=None,
            token_usage=TokenUsage(),
            cost_usd=CostUsd(),
            llm_call_count=0,
            started_at=_utcnow(),
            ended_at=None,
            latency_ms=None,
            error_message=None,
            error_stack=None,
        )
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    repo = SqlAlchemyAgentRunRepository(session)
                    await repo.save_run(run)
        except Exception as e:
            self._logger.error(
                "AgentRun start_run failed",
                exception=e,
                run_id=run_id.value,
                user_id=user_id,
            )
            raise RuntimeError("Failed to start AgentRun observability") from e
        self._logger.info(
            "AgentRun started",
            run_id=run_id.value,
            user_id=user_id,
            agent_id=agent_id,
        )
        return run_id

    # ── complete_run (best-effort SUM UPDATE) ─────────────────────────
    async def complete_run(
        self,
        run_id: RunId,
        langsmith_trace_id: Optional[str] = None,
        langsmith_run_url: Optional[str] = None,
    ) -> None:
        """SUM(ai_llm_call.*) → ai_run 합계 + status=SUCCESS. 실패는 warning."""
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    repo = SqlAlchemyAgentRunRepository(session)
                    await repo.apply_completion_totals(
                        run_id,
                        langsmith_trace_id=langsmith_trace_id,
                        langsmith_run_url=langsmith_run_url,
                    )
            self._logger.info(
                "AgentRun completed",
                run_id=run_id.value,
                langsmith_trace_id=langsmith_trace_id,
            )
        except Exception as e:
            self._logger.warning(
                "AgentRun complete_run failed (best-effort)",
                exception=e,
                run_id=run_id.value,
            )

    # ── fail_run (best-effort FAILED transition) ──────────────────────
    async def fail_run(self, run_id: RunId, exception: BaseException) -> None:
        """status=FAILED + error_message/stack 기록. 본 호출자에게 raise 안함."""
        message = str(exception)[:1024] if exception else None
        stack = (
            "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))[
                :4096
            ]
            if exception
            else None
        )
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    repo = SqlAlchemyAgentRunRepository(session)
                    await repo.mark_failed(run_id, message, stack)
            self._logger.error(
                "AgentRun failed",
                exception=exception,
                run_id=run_id.value,
            )
        except Exception as e:
            self._logger.warning(
                "AgentRun fail_run write failed (best-effort)",
                exception=e,
                run_id=run_id.value,
            )

    # ── record_step (best-effort) ─────────────────────────────────────
    async def record_step(
        self,
        run_id: RunId,
        step_index: int,
        node_name: str,
        node_type: NodeType,
        llm_model_id: Optional[str],
        status: StepStatus,
        input_summary: Optional[str] = None,
        output_summary: Optional[str] = None,
        error_text: Optional[str] = None,
    ) -> Optional[str]:
        step_id = str(uuid.uuid4())
        step = AgentRunStep(
            id=step_id,
            run_id=run_id,
            step_index=step_index,
            node_name=node_name,
            node_type=node_type,
            llm_model_id=llm_model_id,
            status=status,
            input_summary=input_summary,
            output_summary=output_summary,
            started_at=_utcnow(),
            ended_at=None,
            latency_ms=None,
            error_text=error_text,
        )
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    repo = SqlAlchemyAgentRunRepository(session)
                    await repo.save_step(step)
            return step_id
        except Exception as e:
            self._logger.warning(
                "Tracker record_step failed (best-effort)",
                exception=e,
                run_id=run_id.value,
                node_name=node_name,
            )
            return None

    async def update_step(
        self,
        step_id: str,
        run_id: RunId,
        status: StepStatus,
        output_summary: Optional[str] = None,
        error_text: Optional[str] = None,
    ) -> None:
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    repo = SqlAlchemyAgentRunRepository(session)
                    # 부분 갱신을 위해 fetch 후 변경 (간단 구현; 추후 set-based UPDATE로 최적화)
                    steps = await repo.find_steps(run_id)
                    target = next((s for s in steps if s.id == step_id), None)
                    if target is None:
                        return
                    target.status = status
                    if output_summary is not None:
                        target.output_summary = output_summary
                    if error_text is not None:
                        target.error_text = error_text
                    target.ended_at = _utcnow()
                    target.latency_ms = _compute_latency_ms(
                        target.started_at, target.ended_at
                    )
                    await repo.update_step(target)
        except Exception as e:
            self._logger.warning(
                "Tracker update_step failed (best-effort)",
                exception=e,
                run_id=run_id.value,
                step_id=step_id,
            )

    # ── record_tool_call (best-effort) ────────────────────────────────
    async def record_tool_call(
        self,
        run_id: RunId,
        step_id: Optional[str],
        tool_name: str,
        arguments: Optional[dict],
        result_summary: Optional[str] = None,
        latency_ms: Optional[int] = None,
        status: str = "STARTED",
        llm_model_id: Optional[str] = None,
        error_text: Optional[str] = None,
    ) -> Optional[str]:
        tool_call_id = str(uuid.uuid4())
        call = ToolCall(
            id=tool_call_id,
            run_id=run_id,
            step_id=step_id,
            tool_name=tool_name,
            llm_model_id=llm_model_id,
            arguments_json=arguments,
            result_summary=result_summary,
            result_json=None,
            token_usage=None,
            total_cost_usd=None,
            latency_ms=latency_ms,
            status=status,
            error_text=error_text,
            created_at=_utcnow(),
        )
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    repo = SqlAlchemyAgentRunRepository(session)
                    await repo.save_tool_call(call)
            return tool_call_id
        except Exception as e:
            self._logger.warning(
                "Tracker record_tool_call failed (best-effort)",
                exception=e,
                run_id=run_id.value,
                tool_name=tool_name,
            )
            return None

    async def update_tool_call(
        self,
        tool_call_id: str,
        run_id: RunId,
        status: str,
        result_summary: Optional[str] = None,
        latency_ms: Optional[int] = None,
        llm_model_id: Optional[str] = None,
        error_text: Optional[str] = None,
    ) -> None:
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    repo = SqlAlchemyAgentRunRepository(session)
                    calls = await repo.find_tool_calls(run_id)
                    target = next((c for c in calls if c.id == tool_call_id), None)
                    if target is None:
                        return
                    target.status = status
                    if result_summary is not None:
                        target.result_summary = result_summary
                    if latency_ms is not None:
                        target.latency_ms = latency_ms
                    if llm_model_id is not None:
                        target.llm_model_id = llm_model_id
                    if error_text is not None:
                        target.error_text = error_text
                    await repo.update_tool_call(target)
        except Exception as e:
            self._logger.warning(
                "Tracker update_tool_call failed (best-effort)",
                exception=e,
                run_id=run_id.value,
                tool_call_id=tool_call_id,
            )

    # ── record_retrieval (best-effort) ────────────────────────────────
    async def record_retrieval(
        self,
        run_id: RunId,
        tool_call_id: Optional[str],
        collection_name: str,
        document_id: Optional[str] = None,
        chunk_id: Optional[str] = None,
        score: Optional[float] = None,
        rank_index: Optional[int] = None,
        content_preview: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        src = RetrievalSource(
            id=str(uuid.uuid4()),
            run_id=run_id,
            tool_call_id=tool_call_id,
            collection_name=collection_name,
            document_id=document_id,
            chunk_id=chunk_id,
            score=score,
            rank_index=rank_index,
            content_preview=content_preview,
            metadata_json=metadata,
            created_at=_utcnow(),
        )
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    repo = SqlAlchemyAgentRunRepository(session)
                    await repo.save_retrieval(src)
        except Exception as e:
            self._logger.warning(
                "Tracker record_retrieval failed (best-effort)",
                exception=e,
                run_id=run_id.value,
                collection=collection_name,
            )

    # ── record_llm_call (best-effort, UsageCallback 호출 진입점) ───────
    async def record_llm_call(
        self,
        run_id: RunId,
        step_id: Optional[str],
        tool_call_id: Optional[str],
        user_id: str,
        agent_id: str,
        provider: str,
        model_name: str,
        purpose: Optional[RunPurpose],
        token_usage: TokenUsage,
        latency_ms: Optional[int],
        status: str,
        error_text: Optional[str] = None,
    ) -> None:
        """UsageCallback에서 호출. model_name→llm_model_id 매핑 + 가격조회 + 비용계산 + INSERT."""
        try:
            llm_model_id = await self._resolver.resolve(provider, model_name)
        except Exception as e:
            self._logger.warning(
                "ModelNameResolver failed (treated as unmapped)",
                exception=e,
                provider=provider,
                model_name=model_name,
            )
            llm_model_id = None

        input_price: Optional[Decimal] = None
        output_price: Optional[Decimal] = None
        if llm_model_id is not None:
            try:
                input_price, output_price = await self._cost_calc.get_pricing(
                    llm_model_id
                )
            except Exception as e:
                self._logger.warning(
                    "CostCalculator pricing lookup failed (cost will be 0)",
                    exception=e,
                    llm_model_id=llm_model_id,
                )

        cost_usd = CostCalculationPolicy.compute(token_usage, input_price, output_price)

        call = LlmCall(
            id=str(uuid.uuid4()),
            run_id=run_id,
            step_id=step_id,
            tool_call_id=tool_call_id,
            user_id=user_id,
            agent_id=agent_id,
            llm_model_id=llm_model_id,
            provider=provider,
            model_name=model_name,
            purpose=purpose,
            token_usage=token_usage,
            input_price_per_1k_usd=input_price,
            output_price_per_1k_usd=output_price,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            status=status,
            error_text=error_text,
            created_at=_utcnow(),
        )
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    repo = SqlAlchemyLlmCallRepository(session)
                    await repo.save(call)
            self._logger.info(
                "LLM call recorded",
                run_id=run_id.value,
                provider=provider,
                model=model_name,
                prompt=token_usage.prompt_tokens,
                completion=token_usage.completion_tokens,
                total_cost_usd=str(cost_usd.total_usd),
                purpose=purpose.value if purpose else None,
            )
        except Exception as e:
            self._logger.warning(
                "Tracker record_llm_call failed (best-effort)",
                exception=e,
                run_id=run_id.value,
                provider=provider,
                model_name=model_name,
            )
