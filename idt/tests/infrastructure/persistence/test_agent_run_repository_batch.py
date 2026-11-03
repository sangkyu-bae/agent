"""런 묶음 일괄 조회 — agent-run-source-citations Design §3.4.

세션 메시지 수와 무관하게 쿼리 횟수가 고정되어야 한다 (FR-09, N+1 금지).
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.agent_run.value_objects import RunId
from src.infrastructure.persistence.models.agent_run import (
    AgentRunModel,
    RetrievalSourceModel,
    ToolCallModel,
)
from src.infrastructure.persistence.repositories.agent_run_repository import (
    SqlAlchemyAgentRunRepository,
)

T0 = datetime(2026, 11, 2)
RUN_A = "aaaaaaaa-1111-1111-1111-111111111111"
RUN_B = "bbbbbbbb-1111-1111-1111-111111111111"


def _session(rows: list[Any]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    session = MagicMock()
    session.execute = AsyncMock(return_value=result)
    return session


def _run(run_id: str, message_id: int, started: datetime) -> AgentRunModel:
    return AgentRunModel(
        id=run_id, conversation_id="s1", user_message_id=message_id, user_id="7",
        agent_id="agent-1", llm_model_id=None, status="SUCCESS",
        langgraph_thread_id="t", started_at=started, ended_at=None, latency_ms=None,
        prompt_tokens=0, completion_tokens=0, total_tokens=0,
        total_cost_usd=Decimal("0"), llm_call_count=0,
    )


def _retrieval(id_: str, run_id: str) -> RetrievalSourceModel:
    return RetrievalSourceModel(
        id=id_, run_id=run_id, collection_name="kb", created_at=T0,
    )


def _tool_call(id_: str, run_id: str) -> ToolCallModel:
    return ToolCallModel(
        id=id_, run_id=run_id, tool_name="wiki_read", status="SUCCESS",
        created_at=T0,
    )


@pytest.mark.asyncio
class TestFindLatestRunsByUserMessages:
    async def test_later_run_wins_for_same_message(self) -> None:
        # 저장소가 started_at 오름차순으로 읽으므로 뒤 행이 마지막 런이다.
        rows = [
            _run(RUN_A, 10, T0),
            _run(RUN_B, 10, T0 + timedelta(seconds=5)),
        ]
        session = _session(rows)
        latest = await SqlAlchemyAgentRunRepository(session).find_latest_runs_by_user_messages([10])
        assert latest[10].id.value == RUN_B
        assert session.execute.await_count == 1

    async def test_empty_ids_issue_no_query(self) -> None:
        session = _session([])
        assert await SqlAlchemyAgentRunRepository(session).find_latest_runs_by_user_messages([]) == {}
        session.execute.assert_not_awaited()


@pytest.mark.asyncio
class TestFindRetrievalsByRuns:
    async def test_groups_by_run_with_one_query(self) -> None:
        session = _session([
            _retrieval("r1", RUN_A), _retrieval("r2", RUN_B), _retrieval("r3", RUN_A),
        ])
        found = await SqlAlchemyAgentRunRepository(session).find_retrievals_by_runs(
            [RunId(RUN_A), RunId(RUN_B)],
        )
        assert [r.id for r in found[RUN_A]] == ["r1", "r3"]
        assert [r.id for r in found[RUN_B]] == ["r2"]
        assert session.execute.await_count == 1

    async def test_empty_ids_issue_no_query(self) -> None:
        session = _session([])
        assert await SqlAlchemyAgentRunRepository(session).find_retrievals_by_runs([]) == {}
        session.execute.assert_not_awaited()


@pytest.mark.asyncio
class TestFindToolCallsByRuns:
    async def test_groups_by_run_with_one_query(self) -> None:
        session = _session([_tool_call("t1", RUN_A), _tool_call("t2", RUN_B)])
        found = await SqlAlchemyAgentRunRepository(session).find_tool_calls_by_runs(
            [RunId(RUN_A), RunId(RUN_B)],
        )
        assert [t.id for t in found[RUN_A]] == ["t1"]
        assert [t.id for t in found[RUN_B]] == ["t2"]
        assert session.execute.await_count == 1

    async def test_empty_ids_issue_no_query(self) -> None:
        session = _session([])
        assert await SqlAlchemyAgentRunRepository(session).find_tool_calls_by_runs([]) == {}
        session.execute.assert_not_awaited()
