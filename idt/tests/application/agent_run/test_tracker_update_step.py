"""RunTracker.update_step latency 계산 회귀 검증.

fix-tracker-naive-aware-datetime Design §6.2:
- _compute_latency_ms 헬퍼 (naive/aware 혼합 안전 처리)
- update_step 회귀 케이스: find_steps가 naive started_at을 반환해도 TypeError 미발생

원인 재현: 기존 코드 line 246
    delta = target.ended_at - target.started_at
        → TypeError: can't subtract offset-naive and offset-aware datetimes
"""
from datetime import datetime, timezone, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_run.cost_calculator import CostCalculator
from src.application.agent_run.model_name_resolver import ModelNameResolver
from src.application.agent_run.tracker import RunTracker, _compute_latency_ms
from src.domain.agent_run.entities import AgentRunStep
from src.domain.agent_run.value_objects import NodeType, RunId, StepStatus


RUN_ID = "11111111-1111-1111-1111-111111111111"
STEP_ID = "22222222-2222-2222-2222-222222222222"


# ─────────────────────────────────────────────────────────────────
# _compute_latency_ms 단위 테스트
# ─────────────────────────────────────────────────────────────────

class TestComputeLatencyMs:
    def test_both_aware_returns_correct_ms(self) -> None:
        start = datetime(2026, 5, 24, 6, 17, 9, tzinfo=timezone.utc)
        end = datetime(2026, 5, 24, 6, 17, 11, tzinfo=timezone.utc)
        assert _compute_latency_ms(start, end) == 2000

    def test_started_naive_ended_aware_no_typeerror(self) -> None:
        """원인 재현 케이스: naive started + aware ended."""
        start = datetime(2026, 5, 24, 6, 17, 9)  # naive
        end = datetime(2026, 5, 24, 6, 17, 11, tzinfo=timezone.utc)
        result = _compute_latency_ms(start, end)
        assert result == 2000

    def test_started_aware_ended_naive_no_typeerror(self) -> None:
        start = datetime(2026, 5, 24, 6, 17, 9, tzinfo=timezone.utc)
        end = datetime(2026, 5, 24, 6, 17, 11)  # naive
        result = _compute_latency_ms(start, end)
        assert result == 2000

    def test_both_naive_assumes_utc_and_computes(self) -> None:
        start = datetime(2026, 5, 24, 6, 17, 9)  # naive
        end = datetime(2026, 5, 24, 6, 17, 11)   # naive
        result = _compute_latency_ms(start, end)
        assert result == 2000

    def test_started_none_returns_none(self) -> None:
        end = datetime(2026, 5, 24, 6, 17, 11, tzinfo=timezone.utc)
        assert _compute_latency_ms(None, end) is None

    def test_ended_none_returns_none(self) -> None:
        start = datetime(2026, 5, 24, 6, 17, 9, tzinfo=timezone.utc)
        assert _compute_latency_ms(start, None) is None

    def test_both_none_returns_none(self) -> None:
        assert _compute_latency_ms(None, None) is None


# ─────────────────────────────────────────────────────────────────
# update_step 통합 회귀 테스트
# ─────────────────────────────────────────────────────────────────

class _FakeSessionFactory:
    """tracker가 직접 호출하는 async_sessionmaker mock."""

    def __init__(self) -> None:
        self.sessions_created = 0

    def __call__(self) -> "_FakeSession":
        self.sessions_created += 1
        return _FakeSession()


class _FakeSession:
    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *a: Any) -> None:
        return None

    def begin(self) -> "_FakeTransaction":
        return _FakeTransaction()


class _FakeTransaction:
    async def __aenter__(self) -> "_FakeTransaction":
        return self

    async def __aexit__(self, *a: Any) -> None:
        return None


def _make_tracker() -> tuple[RunTracker, MagicMock]:
    factory = _FakeSessionFactory()
    cost_calc = MagicMock(spec=CostCalculator)
    resolver = MagicMock(spec=ModelNameResolver)
    logger = MagicMock()
    tracker = RunTracker(
        session_factory=factory,
        cost_calculator=cost_calc,
        model_name_resolver=resolver,
        logger=logger,
    )
    return tracker, logger


def _make_step(started_at: datetime, ended_at: datetime | None = None) -> AgentRunStep:
    return AgentRunStep(
        id=STEP_ID,
        run_id=RunId(RUN_ID),
        step_index=1,
        node_name="answer",
        node_type=NodeType.WORKER,
        llm_model_id=None,
        status=StepStatus.STARTED,
        input_summary=None,
        output_summary=None,
        started_at=started_at,
        ended_at=ended_at,
        latency_ms=None,
        error_text=None,
    )


class TestUpdateStepLatency:
    @pytest.mark.asyncio
    async def test_naive_started_at_does_not_raise_typeerror(self) -> None:
        """회귀: mapper 우회 경로에서 naive started_at이 들어와도 TypeError 미발생."""
        tracker, logger = _make_tracker()
        # find_steps가 naive started_at을 가진 step을 반환
        naive_step = _make_step(started_at=datetime(2026, 5, 24, 6, 17, 9))

        with patch(
            "src.application.agent_run.tracker.SqlAlchemyAgentRunRepository"
        ) as RepoCls:
            repo = RepoCls.return_value
            repo.find_steps = AsyncMock(return_value=[naive_step])
            repo.update_step = AsyncMock(return_value=None)

            await tracker.update_step(
                step_id=STEP_ID,
                run_id=RunId(RUN_ID),
                status=StepStatus.SUCCESS,
                output_summary="done",
            )

            repo.update_step.assert_awaited_once()
            updated: AgentRunStep = repo.update_step.await_args.args[0]
            assert updated.status == StepStatus.SUCCESS
            assert updated.output_summary == "done"
            assert updated.ended_at is not None
            assert updated.ended_at.tzinfo == timezone.utc
            assert updated.latency_ms is not None
            assert updated.latency_ms >= 0

        # best-effort WARNING이 발생하지 않아야 함 (정상 경로)
        logger.warning.assert_not_called()

    @pytest.mark.asyncio
    async def test_aware_started_at_normal_path(self) -> None:
        tracker, logger = _make_tracker()
        aware_step = _make_step(
            started_at=datetime(2026, 5, 24, 6, 17, 9, tzinfo=timezone.utc)
        )

        with patch(
            "src.application.agent_run.tracker.SqlAlchemyAgentRunRepository"
        ) as RepoCls:
            repo = RepoCls.return_value
            repo.find_steps = AsyncMock(return_value=[aware_step])
            repo.update_step = AsyncMock(return_value=None)

            await tracker.update_step(
                step_id=STEP_ID,
                run_id=RunId(RUN_ID),
                status=StepStatus.SUCCESS,
            )

            updated: AgentRunStep = repo.update_step.await_args.args[0]
            assert updated.latency_ms is not None and updated.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_step_id_not_found_early_return(self) -> None:
        tracker, logger = _make_tracker()
        # find_steps가 빈 리스트 반환 → target=None → early return
        with patch(
            "src.application.agent_run.tracker.SqlAlchemyAgentRunRepository"
        ) as RepoCls:
            repo = RepoCls.return_value
            repo.find_steps = AsyncMock(return_value=[])
            repo.update_step = AsyncMock(return_value=None)

            await tracker.update_step(
                step_id="not-exist",
                run_id=RunId(RUN_ID),
                status=StepStatus.SUCCESS,
            )

            repo.update_step.assert_not_called()

    @pytest.mark.asyncio
    async def test_status_and_error_text_updated(self) -> None:
        tracker, logger = _make_tracker()
        naive_step = _make_step(started_at=datetime(2026, 5, 24, 6, 17, 9))

        with patch(
            "src.application.agent_run.tracker.SqlAlchemyAgentRunRepository"
        ) as RepoCls:
            repo = RepoCls.return_value
            repo.find_steps = AsyncMock(return_value=[naive_step])
            repo.update_step = AsyncMock(return_value=None)

            await tracker.update_step(
                step_id=STEP_ID,
                run_id=RunId(RUN_ID),
                status=StepStatus.FAILED,
                error_text="node crashed",
            )

            updated: AgentRunStep = repo.update_step.await_args.args[0]
            assert updated.status == StepStatus.FAILED
            assert updated.error_text == "node crashed"

    @pytest.mark.asyncio
    async def test_db_failure_swallowed_as_warning(self) -> None:
        """best-effort 정책 회귀 검증."""
        tracker, logger = _make_tracker()
        naive_step = _make_step(started_at=datetime(2026, 5, 24, 6, 17, 9))

        with patch(
            "src.application.agent_run.tracker.SqlAlchemyAgentRunRepository"
        ) as RepoCls:
            repo = RepoCls.return_value
            repo.find_steps = AsyncMock(return_value=[naive_step])
            repo.update_step = AsyncMock(side_effect=RuntimeError("db down"))

            # 예외 전파 금지
            await tracker.update_step(
                step_id=STEP_ID,
                run_id=RunId(RUN_ID),
                status=StepStatus.SUCCESS,
            )

            logger.warning.assert_called()
