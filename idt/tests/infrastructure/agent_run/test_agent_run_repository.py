"""SqlAlchemyAgentRunRepository unit tests — AsyncMock 사용 (CRUD 매핑 검증)."""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.agent_run.entities import (
    AgentRun,
    AgentRunStep,
    RetrievalSource,
    ToolCall,
)
from src.domain.agent_run.interfaces import RunListFilters
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
from src.infrastructure.persistence.repositories.agent_run_repository import (
    SqlAlchemyAgentRunRepository,
)

RUN_ID = "11111111-1111-1111-1111-111111111111"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_run(status: RunStatus = RunStatus.RUNNING) -> AgentRun:
    return AgentRun(
        id=RunId(RUN_ID),
        conversation_id="conv-1",
        user_id="user-1",
        agent_id="agent-1",
        llm_model_id="m-1",
        user_message_id=None,
        status=status,
        langgraph_thread_id="conv-1",
        langsmith_trace_id=None,
        langsmith_run_url=None,
        token_usage=TokenUsage(),
        cost_usd=CostUsd(),
        llm_call_count=0,
        started_at=_now(),
        ended_at=None,
        latency_ms=None,
        error_message=None,
        error_stack=None,
    )


def _mock_session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


class TestSaveRun:
    @pytest.mark.asyncio
    async def test_save_run_adds_orm_row_with_running_status(self) -> None:
        session = _mock_session()
        repo = SqlAlchemyAgentRunRepository(session)
        run = _make_run()

        result = await repo.save_run(run)

        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        added = session.add.call_args[0][0]
        assert isinstance(added, AgentRunModel)
        assert added.id == RUN_ID
        assert added.status == "RUNNING"
        assert added.user_id == "user-1"
        assert result is run


class TestFindRun:
    @pytest.mark.asyncio
    async def test_find_run_returns_none_when_missing(self) -> None:
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute.return_value = result_mock

        repo = SqlAlchemyAgentRunRepository(session)
        run = await repo.find_run(RunId(RUN_ID))
        assert run is None

    @pytest.mark.asyncio
    async def test_find_run_returns_domain_object(self) -> None:
        session = _mock_session()
        now = _now()
        orm_row = AgentRunModel(
            id=RUN_ID,
            conversation_id="conv-1",
            user_id="user-1",
            agent_id="agent-1",
            llm_model_id="m-1",
            user_message_id=42,
            status="SUCCESS",
            langgraph_thread_id="conv-1",
            langsmith_trace_id="trace-x",
            langsmith_run_url="https://smith/abc",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            total_cost_usd=Decimal("0.005"),
            llm_call_count=2,
            started_at=now,
            ended_at=now,
            latency_ms=1500,
            error_message=None,
            error_stack=None,
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = orm_row
        session.execute.return_value = result_mock

        repo = SqlAlchemyAgentRunRepository(session)
        run = await repo.find_run(RunId(RUN_ID))

        assert run is not None
        assert run.status is RunStatus.SUCCESS
        assert run.token_usage.total_tokens == 30
        assert run.llm_call_count == 2
        assert run.langsmith_trace_id == "trace-x"


class TestApplyCompletionTotals:
    @pytest.mark.asyncio
    async def test_apply_completion_totals_executes_sum_update_sql(self) -> None:
        session = _mock_session()
        repo = SqlAlchemyAgentRunRepository(session)

        await repo.apply_completion_totals(
            RunId(RUN_ID), langsmith_trace_id="trace-x", langsmith_run_url=None
        )

        session.execute.assert_awaited_once()
        sql_obj = session.execute.await_args.args[0]
        params = session.execute.await_args.args[1]
        sql = str(sql_obj)
        assert "UPDATE ai_run" in sql
        assert "SUM(prompt_tokens)" in sql
        assert "SUM(completion_tokens)" in sql
        assert "SUM(total_tokens)" in sql
        assert "SUM(total_cost_usd)" in sql
        assert "COUNT(*)" in sql
        assert "status = 'SUCCESS'" in sql
        assert "status = 'RUNNING'" in sql  # idempotent guard
        assert params == {
            "rid": RUN_ID,
            "trace_id": "trace-x",
            "run_url": None,
        }
        session.flush.assert_awaited_once()


class TestMarkFailed:
    @pytest.mark.asyncio
    async def test_mark_failed_issues_update_statement(self) -> None:
        session = _mock_session()
        repo = SqlAlchemyAgentRunRepository(session)

        await repo.mark_failed(
            RunId(RUN_ID),
            error_message="boom",
            error_stack="trace",
        )

        session.execute.assert_awaited_once()
        session.flush.assert_awaited_once()


class TestSaveStep:
    @pytest.mark.asyncio
    async def test_save_step_adds_orm_with_node_type(self) -> None:
        session = _mock_session()
        repo = SqlAlchemyAgentRunRepository(session)
        step = AgentRunStep(
            id="step-1",
            run_id=RunId(RUN_ID),
            step_index=0,
            node_name="supervisor",
            node_type=NodeType.SUPERVISOR,
            llm_model_id="m-1",
            status=StepStatus.STARTED,
            input_summary="hi",
            output_summary=None,
            started_at=_now(),
            ended_at=None,
            latency_ms=None,
            error_text=None,
        )

        await repo.save_step(step)

        added = session.add.call_args[0][0]
        assert isinstance(added, AgentRunStepModel)
        assert added.node_type == "SUPERVISOR"
        assert added.status == "STARTED"


class TestSaveToolCall:
    @pytest.mark.asyncio
    async def test_save_tool_call_with_json_arguments(self) -> None:
        session = _mock_session()
        repo = SqlAlchemyAgentRunRepository(session)
        call = ToolCall(
            id="tool-1",
            run_id=RunId(RUN_ID),
            step_id="step-1",
            tool_name="rag_search",
            llm_model_id=None,
            arguments_json={"query": "hi", "top_k": 5},
            result_summary=None,
            result_json=None,
            token_usage=None,
            total_cost_usd=None,
            latency_ms=None,
            status="STARTED",
            error_text=None,
            created_at=_now(),
        )

        await repo.save_tool_call(call)

        added = session.add.call_args[0][0]
        assert isinstance(added, ToolCallModel)
        assert added.arguments_json == {"query": "hi", "top_k": 5}
        assert added.status == "STARTED"


class TestSaveRetrieval:
    @pytest.mark.asyncio
    async def test_save_retrieval_stores_chunk_info(self) -> None:
        session = _mock_session()
        repo = SqlAlchemyAgentRunRepository(session)
        src = RetrievalSource(
            id="ret-1",
            run_id=RunId(RUN_ID),
            tool_call_id="tool-1",
            collection_name="policy_kb",
            document_id="doc-1",
            chunk_id="chunk-1",
            score=0.87,
            rank_index=0,
            content_preview="preview",
            metadata_json={"source": "pdf"},
            created_at=_now(),
        )

        await repo.save_retrieval(src)

        added = session.add.call_args[0][0]
        assert isinstance(added, RetrievalSourceModel)
        assert added.collection_name == "policy_kb"
        assert added.rank_index == 0


class TestListRuns:
    """M5-4: list_runs / count_runs SQL — 필터 + pagination + COUNT."""

    @pytest.mark.asyncio
    async def test_list_runs_applies_filters_and_pagination(self) -> None:
        session = _mock_session()
        result_mock = MagicMock()
        # 빈 결과로 단순 검증 (SQL 컴파일 결과만 확인)
        result_mock.scalars.return_value.all.return_value = []
        session.execute.return_value = result_mock

        repo = SqlAlchemyAgentRunRepository(session)
        filters = RunListFilters(
            from_dt=datetime(2026, 5, 1, tzinfo=timezone.utc),
            to_dt=datetime(2026, 5, 31, tzinfo=timezone.utc),
            user_id="user-1",
            status="FAILED",
            limit=10,
            offset=20,
        )
        await repo.list_runs(filters)

        # session.execute called with statement
        assert session.execute.called
        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        # 필터 조건 모두 포함
        assert "ai_run" in compiled.lower()
        assert "started_at" in compiled.lower()
        assert "user_id" in compiled
        assert "status" in compiled
        # LIMIT/OFFSET
        assert "limit" in compiled.lower() or "LIMIT" in compiled
        assert "offset" in compiled.lower() or "OFFSET" in compiled

    @pytest.mark.asyncio
    async def test_list_runs_orders_by_started_at_desc(self) -> None:
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute.return_value = result_mock

        repo = SqlAlchemyAgentRunRepository(session)
        await repo.list_runs(RunListFilters())

        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "ORDER BY" in compiled.upper()
        assert "started_at" in compiled.lower()
        assert "DESC" in compiled.upper()

    @pytest.mark.asyncio
    async def test_count_runs_returns_total_with_same_filters(self) -> None:
        """★ 회귀 가드: list와 같은 WHERE 조건 적용."""
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = 137
        session.execute.return_value = result_mock

        repo = SqlAlchemyAgentRunRepository(session)
        filters = RunListFilters(user_id="user-1", status="FAILED")
        total = await repo.count_runs(filters)

        assert total == 137
        stmt = session.execute.call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "count" in compiled.lower()
        # 같은 필터 적용
        assert "user_id" in compiled
        assert "status" in compiled

    @pytest.mark.asyncio
    async def test_list_runs_handles_no_filters(self) -> None:
        session = _mock_session()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute.return_value = result_mock

        repo = SqlAlchemyAgentRunRepository(session)
        await repo.list_runs(RunListFilters())  # all None except default limit/offset

        # 정상 호출됨
        assert session.execute.called
