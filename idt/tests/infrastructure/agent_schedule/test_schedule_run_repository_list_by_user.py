"""ScheduleRunRepository.list_by_user 단위 테스트 (background-jobs §7-7).

Mock AsyncSession — 소유자 필터·조인·정렬·튜플 매핑을 검증한다.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infrastructure.agent_schedule.models import AgentScheduleRunModel
from src.infrastructure.agent_schedule.schedule_run_repository import (
    ScheduleRunRepository,
)

_NOW = datetime(2026, 8, 11, 3, 0)


def _run_model(**overrides) -> AgentScheduleRunModel:
    base = dict(
        id="r1",
        schedule_id="s1",
        agent_id="a1",
        status="success",
        scheduled_for=_NOW,
        started_at=_NOW,
        finished_at=_NOW,
        session_id="sess-9",
        run_id="run-9",
        error_message=None,
        request_id="req-0",
    )
    base.update(overrides)
    return AgentScheduleRunModel(**base)


def _exec_result(rows=None):
    result = MagicMock()
    result.all.return_value = rows or []
    return result


@pytest.fixture
def mock_session():
    return AsyncMock()


class TestListByUser:
    @pytest.mark.asyncio
    async def test_maps_rows_to_run_name_agent_tuples(self, mock_session):
        mock_session.execute = AsyncMock(
            return_value=_exec_result(
                rows=[(_run_model(), "아침 요약", "리서치 봇")]
            )
        )
        repo = ScheduleRunRepository(mock_session, MagicMock())
        rows = await repo.list_by_user("u1", 20, 0, "req-1")
        assert len(rows) == 1
        run, schedule_name, agent_name = rows[0]
        assert run.id == "r1"
        assert schedule_name == "아침 요약"
        assert agent_name == "리서치 봇"

    @pytest.mark.asyncio
    async def test_statement_filters_owner_and_orders_desc(self, mock_session):
        mock_session.execute = AsyncMock(return_value=_exec_result())
        repo = ScheduleRunRepository(mock_session, MagicMock())
        assert await repo.list_by_user("u1", 20, 0, "req-1") == []
        sql = str(mock_session.execute.call_args[0][0])
        assert "JOIN agent_schedule " in sql
        assert "LEFT OUTER JOIN agent_definition" in sql
        assert "agent_schedule.user_id" in sql
        assert "ORDER BY agent_schedule_run.started_at DESC" in sql
