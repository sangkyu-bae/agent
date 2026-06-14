"""SqlAlchemyLlmCallRepository unit tests — AsyncMock + 집계 쿼리 검증."""
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.agent_run.entities import LlmCall
from src.domain.agent_run.interfaces import (
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
from src.infrastructure.persistence.models.agent_run import LlmCallModel
from src.infrastructure.persistence.repositories.llm_call_repository import (
    SqlAlchemyLlmCallRepository,
)

RUN_ID = "11111111-1111-1111-1111-111111111111"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mock_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


def _make_call() -> LlmCall:
    return LlmCall(
        id="llm-1",
        run_id=RunId(RUN_ID),
        step_id=None,
        tool_call_id=None,
        user_id="user-1",
        agent_id="agent-1",
        llm_model_id="m-1",
        provider="openai",
        model_name="gpt-4o",
        purpose=RunPurpose.SUPERVISOR,
        token_usage=TokenUsage(100, 50, 150),
        input_price_per_1k_usd=Decimal("0.005"),
        output_price_per_1k_usd=Decimal("0.015"),
        cost_usd=CostUsd(
            input_usd=Decimal("0.000500"),
            output_usd=Decimal("0.000750"),
            total_usd=Decimal("0.001250"),
        ),
        latency_ms=1200,
        status="SUCCESS",
        error_text=None,
        created_at=_now(),
    )


class TestSave:
    @pytest.mark.asyncio
    async def test_save_persists_with_denormalized_fields(self) -> None:
        session = _mock_session()
        repo = SqlAlchemyLlmCallRepository(session)
        call = _make_call()

        await repo.save(call)

        added = session.add.call_args[0][0]
        assert isinstance(added, LlmCallModel)
        assert added.user_id == "user-1"
        assert added.agent_id == "agent-1"
        assert added.model_name == "gpt-4o"
        assert added.provider == "openai"
        assert added.purpose == "supervisor"
        assert added.total_tokens == 150
        assert added.input_cost_usd == Decimal("0.000500")
        assert added.total_cost_usd == Decimal("0.001250")

    @pytest.mark.asyncio
    async def test_save_handles_none_purpose(self) -> None:
        session = _mock_session()
        repo = SqlAlchemyLlmCallRepository(session)
        call = _make_call()
        call.purpose = None

        await repo.save(call)

        added = session.add.call_args[0][0]
        assert added.purpose is None


class TestAggregateByUser:
    @pytest.mark.asyncio
    async def test_aggregate_by_user_returns_rows_grouped_by_user(self) -> None:
        session = _mock_session()
        # 3 사용자 × 2일 시드 결과 시뮬레이션
        result_mock = MagicMock()
        result_mock.all.return_value = [
            MagicMock(user_id="user-a", tokens=1000, cost=Decimal("0.010"), calls=5),
            MagicMock(user_id="user-b", tokens=500, cost=Decimal("0.005"), calls=3),
            MagicMock(user_id="user-c", tokens=200, cost=Decimal("0.002"), calls=1),
        ]
        session.execute.return_value = result_mock

        repo = SqlAlchemyLlmCallRepository(session)
        rows = await repo.aggregate_by_user(
            datetime(2026, 5, 1, tzinfo=timezone.utc),
            datetime(2026, 5, 31, tzinfo=timezone.utc),
        )

        assert len(rows) == 3
        assert rows[0] == UserUsageRow(
            user_id="user-a",
            total_tokens=1000,
            total_cost_usd=Decimal("0.010"),
            call_count=5,
        )


class TestAggregateByLlmModel:
    @pytest.mark.asyncio
    async def test_aggregate_by_llm_model_groups_by_model(self) -> None:
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.all.return_value = [
            MagicMock(
                model_id="m-1",
                provider="openai",
                model_name="gpt-4o",
                tokens=1200000,
                cost=Decimal("18.0"),
                calls=50,
            ),
            MagicMock(
                model_id="m-2",
                provider="anthropic",
                model_name="claude-3-5-sonnet",
                tokens=800000,
                cost=Decimal("12.0"),
                calls=30,
            ),
        ]
        session.execute.return_value = result_mock

        repo = SqlAlchemyLlmCallRepository(session)
        rows = await repo.aggregate_by_llm_model(
            datetime(2026, 5, 1, tzinfo=timezone.utc),
            datetime(2026, 5, 31, tzinfo=timezone.utc),
        )

        assert len(rows) == 2
        assert rows[0] == LlmUsageRow(
            llm_model_id="m-1",
            provider="openai",
            model_name="gpt-4o",
            total_tokens=1200000,
            total_cost_usd=Decimal("18.0"),
            call_count=50,
        )


class TestAggregateUserXLlm:
    @pytest.mark.asyncio
    async def test_aggregate_user_x_llm_filters_by_user(self) -> None:
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.all.return_value = [
            MagicMock(
                model_id="m-1",
                provider="openai",
                model_name="gpt-4o",
                tokens=10000,
                cost=Decimal("0.15"),
                calls=4,
            ),
        ]
        session.execute.return_value = result_mock

        repo = SqlAlchemyLlmCallRepository(session)
        rows = await repo.aggregate_user_x_llm(
            "user-1",
            datetime(2026, 5, 1, tzinfo=timezone.utc),
            datetime(2026, 5, 31, tzinfo=timezone.utc),
        )

        assert len(rows) == 1
        assert rows[0].llm_model_id == "m-1"
        assert rows[0].total_tokens == 10000


class TestAggregateByNode:
    """M4-3: ai_llm_call JOIN ai_run_step GROUP BY node_name."""

    @pytest.mark.asyncio
    async def test_aggregate_by_node_returns_rows_grouped_by_node_name(self) -> None:
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.all.return_value = [
            MagicMock(
                node_name="supervisor",
                tokens=5000,
                cost=Decimal("0.050"),
                calls=10,
            ),
            MagicMock(
                node_name="worker_finance",
                tokens=20000,
                cost=Decimal("0.300"),
                calls=20,
            ),
            MagicMock(
                node_name="final_answer",
                tokens=15000,
                cost=Decimal("0.450"),
                calls=10,
            ),
        ]
        session.execute.return_value = result_mock

        repo = SqlAlchemyLlmCallRepository(session)
        rows = await repo.aggregate_by_node(
            datetime(2026, 5, 1, tzinfo=timezone.utc),
            datetime(2026, 5, 31, tzinfo=timezone.utc),
        )

        assert len(rows) == 3
        assert rows[0] == NodeUsageRow(
            node_name="supervisor",
            call_count=10,
            total_tokens=5000,
            total_cost_usd=Decimal("0.050"),
        )
        assert rows[2].node_name == "final_answer"
        assert rows[2].total_cost_usd == Decimal("0.450")

    @pytest.mark.asyncio
    async def test_aggregate_by_node_uses_inner_join_via_step_id(self) -> None:
        """INNER JOIN ai_run_step → step_id NULL인 행은 자연 제외."""
        from src.infrastructure.persistence.models.agent_run import (
            AgentRunStepModel,
            LlmCallModel,
        )

        session = _mock_session()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        session.execute.return_value = result_mock

        repo = SqlAlchemyLlmCallRepository(session)
        await repo.aggregate_by_node(
            datetime(2026, 5, 1, tzinfo=timezone.utc),
            datetime(2026, 5, 31, tzinfo=timezone.utc),
        )

        # session.execute 호출됨 — 실제 SQL에 JOIN 포함되는지는 컴파일된 statement 검사
        assert session.execute.called
        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "ai_run_step" in compiled
        assert "node_name" in compiled

    @pytest.mark.asyncio
    async def test_aggregate_by_node_respects_from_to_window(self) -> None:
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        session.execute.return_value = result_mock

        repo = SqlAlchemyLlmCallRepository(session)
        from_dt = datetime(2026, 5, 1, tzinfo=timezone.utc)
        to_dt = datetime(2026, 5, 31, tzinfo=timezone.utc)
        await repo.aggregate_by_node(from_dt, to_dt)

        # SQL이 between으로 컴파일되는지 검사
        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        # SQLAlchemy의 between은 BETWEEN으로 컴파일
        assert "BETWEEN" in compiled.upper() or "created_at" in compiled


class TestAggregateSummary:
    """M5: 카드 4종 단일 응답 — tokens/cost(ai_llm_call) + run 수(ai_run)."""

    @pytest.mark.asyncio
    async def test_aggregate_summary_combines_two_subqueries(self) -> None:
        """token 합계 + run 카운트를 2회 execute 로 조회하여 단일 row 반환."""
        session = _mock_session()
        token_row = MagicMock(tokens=12345, cost=Decimal("0.456789"))
        run_row = MagicMock(total_runs=10, success_runs=9, failed_runs=1)
        token_result = MagicMock()
        token_result.one.return_value = token_row
        run_result = MagicMock()
        run_result.one.return_value = run_row
        session.execute.side_effect = [token_result, run_result]

        repo = SqlAlchemyLlmCallRepository(session)
        from_dt = datetime(2026, 5, 1, tzinfo=timezone.utc)
        to_dt = datetime(2026, 5, 31, tzinfo=timezone.utc)
        result = await repo.aggregate_summary(from_dt, to_dt)

        assert isinstance(result, UsageSummaryRow)
        assert result.total_tokens == 12345
        assert result.total_cost_usd == Decimal("0.456789")
        assert result.total_runs == 10
        assert result.success_runs == 9
        assert result.failed_runs == 1
        assert result.from_dt == from_dt
        assert result.to_dt == to_dt
        # 2번의 execute (token + run)
        assert session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_aggregate_summary_admin_omits_user_filter(self) -> None:
        """admin 컨텍스트(user_id=None) — WHERE 절에 user_id 없음."""
        session = _mock_session()
        token_result = MagicMock()
        token_result.one.return_value = MagicMock(tokens=0, cost=Decimal("0"))
        run_result = MagicMock()
        run_result.one.return_value = MagicMock(
            total_runs=0, success_runs=0, failed_runs=0
        )
        session.execute.side_effect = [token_result, run_result]

        repo = SqlAlchemyLlmCallRepository(session)
        await repo.aggregate_summary(
            datetime(2026, 5, 1, tzinfo=timezone.utc),
            datetime(2026, 5, 31, tzinfo=timezone.utc),
        )

        token_stmt = session.execute.call_args_list[0][0][0]
        run_stmt = session.execute.call_args_list[1][0][0]
        token_compiled = str(
            token_stmt.compile(compile_kwargs={"literal_binds": False})
        )
        run_compiled = str(
            run_stmt.compile(compile_kwargs={"literal_binds": False})
        )
        # admin 모드 — user_id 필터 미적용
        assert "user_id" not in token_compiled
        assert "user_id" not in run_compiled

    @pytest.mark.asyncio
    async def test_aggregate_summary_me_applies_user_filter(self) -> None:
        """me 컨텍스트(user_id 주어짐) — 두 sub-query 모두 user_id 필터 적용."""
        session = _mock_session()
        token_result = MagicMock()
        token_result.one.return_value = MagicMock(tokens=100, cost=Decimal("0.01"))
        run_result = MagicMock()
        run_result.one.return_value = MagicMock(
            total_runs=2, success_runs=2, failed_runs=0
        )
        session.execute.side_effect = [token_result, run_result]

        repo = SqlAlchemyLlmCallRepository(session)
        await repo.aggregate_summary(
            datetime(2026, 5, 1, tzinfo=timezone.utc),
            datetime(2026, 5, 31, tzinfo=timezone.utc),
            user_id="user-7",
        )

        token_compiled = str(
            session.execute.call_args_list[0][0][0].compile(
                compile_kwargs={"literal_binds": False}
            )
        )
        run_compiled = str(
            session.execute.call_args_list[1][0][0].compile(
                compile_kwargs={"literal_binds": False}
            )
        )
        assert "user_id" in token_compiled
        assert "user_id" in run_compiled

    @pytest.mark.asyncio
    async def test_aggregate_summary_uses_status_case_for_success_failed(
        self,
    ) -> None:
        """SQL에 CASE WHEN status='SUCCESS'/'FAILED' 가 포함되어야 한다."""
        session = _mock_session()
        token_result = MagicMock()
        token_result.one.return_value = MagicMock(tokens=0, cost=Decimal("0"))
        run_result = MagicMock()
        run_result.one.return_value = MagicMock(
            total_runs=0, success_runs=0, failed_runs=0
        )
        session.execute.side_effect = [token_result, run_result]

        repo = SqlAlchemyLlmCallRepository(session)
        await repo.aggregate_summary(
            datetime(2026, 5, 1, tzinfo=timezone.utc),
            datetime(2026, 5, 31, tzinfo=timezone.utc),
        )

        run_compiled = str(
            session.execute.call_args_list[1][0][0].compile(
                compile_kwargs={"literal_binds": False}
            )
        ).upper()
        assert "CASE" in run_compiled
        assert "SUCCESS" in run_compiled
        assert "FAILED" in run_compiled


class TestAggregateTimeseries:
    """M5: 일자별 GROUP BY DATE(started_at) — ai_run LEFT JOIN ai_llm_call."""

    @pytest.mark.asyncio
    async def test_aggregate_timeseries_returns_points_in_order(self) -> None:
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.all.return_value = [
            MagicMock(
                bucket=date(2026, 5, 1),
                run_count=3,
                tokens=100,
                cost=Decimal("0.001"),
            ),
            MagicMock(
                bucket=date(2026, 5, 2),
                run_count=5,
                tokens=300,
                cost=Decimal("0.003"),
            ),
        ]
        session.execute.return_value = result_mock

        repo = SqlAlchemyLlmCallRepository(session)
        points = await repo.aggregate_timeseries(
            datetime(2026, 5, 1, tzinfo=timezone.utc),
            datetime(2026, 5, 31, tzinfo=timezone.utc),
        )

        assert len(points) == 2
        assert points[0] == UsageTimeseriesPoint(
            bucket=date(2026, 5, 1),
            run_count=3,
            total_tokens=100,
            total_cost_usd=Decimal("0.001"),
        )
        assert points[1].bucket == date(2026, 5, 2)

    @pytest.mark.asyncio
    async def test_aggregate_timeseries_sql_groups_by_date_with_left_join(
        self,
    ) -> None:
        """SQL: ai_run LEFT JOIN ai_llm_call GROUP BY DATE(started_at)."""
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        session.execute.return_value = result_mock

        repo = SqlAlchemyLlmCallRepository(session)
        await repo.aggregate_timeseries(
            datetime(2026, 5, 1, tzinfo=timezone.utc),
            datetime(2026, 5, 31, tzinfo=timezone.utc),
        )

        compiled = str(
            session.execute.call_args[0][0].compile(
                compile_kwargs={"literal_binds": False}
            )
        )
        assert "ai_run" in compiled
        assert "ai_llm_call" in compiled
        upper = compiled.upper()
        assert "LEFT" in upper and "JOIN" in upper
        assert "GROUP BY" in upper
        assert "DATE" in upper or "CAST" in upper
        assert "ORDER BY" in upper

    @pytest.mark.asyncio
    async def test_aggregate_timeseries_me_applies_user_filter(self) -> None:
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        session.execute.return_value = result_mock

        repo = SqlAlchemyLlmCallRepository(session)
        await repo.aggregate_timeseries(
            datetime(2026, 5, 1, tzinfo=timezone.utc),
            datetime(2026, 5, 31, tzinfo=timezone.utc),
            user_id="user-7",
        )

        compiled = str(
            session.execute.call_args[0][0].compile(
                compile_kwargs={"literal_binds": False}
            )
        )
        assert "user_id" in compiled

    @pytest.mark.asyncio
    async def test_aggregate_timeseries_admin_omits_user_filter(self) -> None:
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.all.return_value = []
        session.execute.return_value = result_mock

        repo = SqlAlchemyLlmCallRepository(session)
        await repo.aggregate_timeseries(
            datetime(2026, 5, 1, tzinfo=timezone.utc),
            datetime(2026, 5, 31, tzinfo=timezone.utc),
        )

        compiled = str(
            session.execute.call_args[0][0].compile(
                compile_kwargs={"literal_binds": False}
            )
        )
        assert "user_id" not in compiled
