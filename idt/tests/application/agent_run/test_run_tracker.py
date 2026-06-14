"""RunTracker: start/complete/fail + record_* best-effort 동작 검증.

Tracker는 세션을 직접 열기 때문에 session_factory를 통째로 mock한다.
"""
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_run.cost_calculator import CostCalculator
from src.application.agent_run.model_name_resolver import ModelNameResolver
from src.application.agent_run.schemas import RunObservabilityConfig
from src.application.agent_run.tracker import RunTracker
from src.domain.agent_run.value_objects import (
    NodeType,
    RunId,
    RunPurpose,
    StepStatus,
    TokenUsage,
)


RUN_ID = "11111111-1111-1111-1111-111111111111"


class _FakeSessionFactory:
    """async_sessionmaker mock — 매번 새 session을 반환하고 transaction context를 흉내낸다.

    operations 리스트에 호출된 Repository 메서드 이름을 누적해 검증할 수 있다.
    """

    def __init__(self) -> None:
        self.operations: list[str] = []
        self.failing = False
        self.sessions_created = 0

    def __call__(self) -> "_FakeSession":
        self.sessions_created += 1
        return _FakeSession(self)


class _FakeSession:
    def __init__(self, parent: _FakeSessionFactory) -> None:
        self._parent = parent

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *a: Any) -> None:
        return None

    def begin(self) -> "_FakeTransaction":
        return _FakeTransaction(self._parent)

    # Repository가 호출할 메서드들 — 더미
    async def execute(self, *a: Any, **k: Any) -> MagicMock:
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalar_one.side_effect = Exception("not used in tracker tests")
        result.scalars.return_value.all.return_value = []
        return result

    async def flush(self) -> None:
        if self._parent.failing:
            raise RuntimeError("flush failed")

    def add(self, _obj: Any) -> None:
        self._parent.operations.append("add")


class _FakeTransaction:
    def __init__(self, parent: _FakeSessionFactory) -> None:
        self._parent = parent

    async def __aenter__(self) -> "_FakeTransaction":
        return self

    async def __aexit__(self, exc_type: Any, *_a: Any) -> None:
        return None


def _make_tracker(
    failing: bool = False,
    resolver_id: str | None = "m-1",
    pricing: tuple[Decimal | None, Decimal | None] = (
        Decimal("0.005"),
        Decimal("0.015"),
    ),
) -> tuple[RunTracker, _FakeSessionFactory, MagicMock]:
    factory = _FakeSessionFactory()
    factory.failing = failing
    cost_calc = MagicMock(spec=CostCalculator)
    cost_calc.get_pricing = AsyncMock(return_value=pricing)
    resolver = MagicMock(spec=ModelNameResolver)
    resolver.resolve = AsyncMock(return_value=resolver_id)
    logger = MagicMock()
    tracker = RunTracker(
        session_factory=factory,
        cost_calculator=cost_calc,
        model_name_resolver=resolver,
        logger=logger,
    )
    return tracker, factory, logger


class TestStartRun:
    @pytest.mark.asyncio
    async def test_start_run_inserts_row_and_returns_run_id(self) -> None:
        tracker, factory, logger = _make_tracker()

        result = await tracker.start_run(
            run_id=RunId(RUN_ID),
            conversation_id="conv-1",
            user_id="user-1",
            agent_id="agent-1",
            agent_llm_model_id="m-1",
            user_message_id=None,
            langgraph_thread_id="conv-1",
        )

        assert result == RunId(RUN_ID)
        assert "add" in factory.operations  # ai_run row added
        logger.info.assert_called()

    @pytest.mark.asyncio
    async def test_start_run_raises_on_db_failure(self) -> None:
        tracker, factory, logger = _make_tracker(failing=True)

        with pytest.raises(RuntimeError, match="Failed to start AgentRun observability"):
            await tracker.start_run(
                run_id=RunId(RUN_ID),
                conversation_id="conv-1",
                user_id="user-1",
                agent_id="agent-1",
                agent_llm_model_id=None,
                user_message_id=None,
                langgraph_thread_id="conv-1",
            )

        logger.error.assert_called()


class TestCompleteRun:
    @pytest.mark.asyncio
    async def test_complete_run_calls_apply_completion_totals(self) -> None:
        tracker, factory, logger = _make_tracker()

        with patch(
            "src.application.agent_run.tracker.SqlAlchemyAgentRunRepository"
        ) as RepoCls:
            repo_inst = RepoCls.return_value
            repo_inst.apply_completion_totals = AsyncMock(return_value=None)

            await tracker.complete_run(
                RunId(RUN_ID), langsmith_trace_id="trace-x"
            )

            repo_inst.apply_completion_totals.assert_awaited_once()
            kwargs = repo_inst.apply_completion_totals.await_args.kwargs
            assert kwargs["langsmith_trace_id"] == "trace-x"
        logger.info.assert_called()

    @pytest.mark.asyncio
    async def test_complete_run_does_not_raise_on_failure(self) -> None:
        tracker, factory, logger = _make_tracker()

        with patch(
            "src.application.agent_run.tracker.SqlAlchemyAgentRunRepository"
        ) as RepoCls:
            RepoCls.return_value.apply_completion_totals = AsyncMock(
                side_effect=RuntimeError("db down")
            )

            # best-effort: 예외 전파 X
            await tracker.complete_run(RunId(RUN_ID))

        logger.warning.assert_called()


class TestFailRun:
    @pytest.mark.asyncio
    async def test_fail_run_marks_failed(self) -> None:
        tracker, factory, logger = _make_tracker()

        with patch(
            "src.application.agent_run.tracker.SqlAlchemyAgentRunRepository"
        ) as RepoCls:
            RepoCls.return_value.mark_failed = AsyncMock(return_value=None)

            await tracker.fail_run(RunId(RUN_ID), RuntimeError("boom"))

            RepoCls.return_value.mark_failed.assert_awaited_once()
            args = RepoCls.return_value.mark_failed.await_args.args
            assert args[0] == RunId(RUN_ID)
            assert args[1] == "boom"  # truncated message
        logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_fail_run_swallows_exception(self) -> None:
        tracker, factory, logger = _make_tracker()

        with patch(
            "src.application.agent_run.tracker.SqlAlchemyAgentRunRepository"
        ) as RepoCls:
            RepoCls.return_value.mark_failed = AsyncMock(
                side_effect=RuntimeError("db down")
            )

            await tracker.fail_run(RunId(RUN_ID), RuntimeError("boom"))

        logger.warning.assert_called()


class TestRecordStep:
    @pytest.mark.asyncio
    async def test_record_step_returns_uuid(self) -> None:
        tracker, factory, logger = _make_tracker()

        with patch(
            "src.application.agent_run.tracker.SqlAlchemyAgentRunRepository"
        ) as RepoCls:
            RepoCls.return_value.save_step = AsyncMock(return_value=None)

            step_id = await tracker.record_step(
                run_id=RunId(RUN_ID),
                step_index=0,
                node_name="supervisor",
                node_type=NodeType.SUPERVISOR,
                llm_model_id="m-1",
                status=StepStatus.STARTED,
            )

            assert step_id is not None
            assert len(step_id) == 36  # UUID
            RepoCls.return_value.save_step.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_step_returns_none_on_failure(self) -> None:
        tracker, factory, logger = _make_tracker()

        with patch(
            "src.application.agent_run.tracker.SqlAlchemyAgentRunRepository"
        ) as RepoCls:
            RepoCls.return_value.save_step = AsyncMock(
                side_effect=RuntimeError("db down")
            )

            step_id = await tracker.record_step(
                run_id=RunId(RUN_ID),
                step_index=0,
                node_name="supervisor",
                node_type=NodeType.SUPERVISOR,
                llm_model_id=None,
                status=StepStatus.STARTED,
            )

            assert step_id is None  # best-effort fail
        logger.warning.assert_called()


class TestRecordLlmCall:
    @pytest.mark.asyncio
    async def test_record_llm_call_computes_cost_with_pricing(self) -> None:
        tracker, factory, logger = _make_tracker(
            resolver_id="m-1",
            pricing=(Decimal("0.005"), Decimal("0.015")),
        )

        with patch(
            "src.application.agent_run.tracker.SqlAlchemyLlmCallRepository"
        ) as RepoCls:
            RepoCls.return_value.save = AsyncMock(return_value=None)

            await tracker.record_llm_call(
                run_id=RunId(RUN_ID),
                step_id=None,
                tool_call_id=None,
                user_id="user-1",
                agent_id="agent-1",
                provider="openai",
                model_name="gpt-4o",
                purpose=RunPurpose.SUPERVISOR,
                token_usage=TokenUsage(1000, 1000, 2000),
                latency_ms=1200,
                status="SUCCESS",
            )

            RepoCls.return_value.save.assert_awaited_once()
            saved_call = RepoCls.return_value.save.await_args.args[0]
            assert saved_call.llm_model_id == "m-1"
            assert saved_call.cost_usd.input_usd == Decimal("0.005000")
            assert saved_call.cost_usd.output_usd == Decimal("0.015000")
            assert saved_call.cost_usd.total_usd == Decimal("0.020000")
            assert saved_call.input_price_per_1k_usd == Decimal("0.005")

    @pytest.mark.asyncio
    async def test_record_llm_call_with_unmapped_model_persists_zero_cost(self) -> None:
        tracker, factory, logger = _make_tracker(
            resolver_id=None,  # unmapped
            pricing=(None, None),
        )

        with patch(
            "src.application.agent_run.tracker.SqlAlchemyLlmCallRepository"
        ) as RepoCls:
            RepoCls.return_value.save = AsyncMock(return_value=None)

            await tracker.record_llm_call(
                run_id=RunId(RUN_ID),
                step_id=None,
                tool_call_id=None,
                user_id="user-1",
                agent_id="agent-1",
                provider="openai",
                model_name="ghost",
                purpose=None,
                token_usage=TokenUsage(100, 100, 200),
                latency_ms=10,
                status="SUCCESS",
            )

            saved_call = RepoCls.return_value.save.await_args.args[0]
            assert saved_call.llm_model_id is None
            assert saved_call.model_name == "ghost"
            assert saved_call.cost_usd.total_usd == Decimal("0")

    @pytest.mark.asyncio
    async def test_record_llm_call_failed_status_persisted(self) -> None:
        tracker, factory, logger = _make_tracker()

        with patch(
            "src.application.agent_run.tracker.SqlAlchemyLlmCallRepository"
        ) as RepoCls:
            RepoCls.return_value.save = AsyncMock(return_value=None)

            await tracker.record_llm_call(
                run_id=RunId(RUN_ID),
                step_id=None,
                tool_call_id=None,
                user_id="user-1",
                agent_id="agent-1",
                provider="openai",
                model_name="gpt-4o",
                purpose=RunPurpose.WORKER,
                token_usage=TokenUsage(),
                latency_ms=10,
                status="FAILED",
                error_text="rate limit",
            )

            saved_call = RepoCls.return_value.save.await_args.args[0]
            assert saved_call.status == "FAILED"
            assert saved_call.error_text == "rate limit"
