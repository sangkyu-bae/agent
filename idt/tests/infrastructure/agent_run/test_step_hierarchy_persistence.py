"""ai_run_step 계층 컬럼(parent_step_id, depth) 영속화 테스트.

Design Ref: subagent-step-observability §3.1/§3.2 / §8.2 B12
Plan SC: SC-1, SC-2, SC-6

V079 로 추가되는 두 컬럼이 저장·조회에서 유지되는지, 계층 미지정(과거 행)이
None/0 으로 읽히는지, update_step 이 계층을 덮어쓰지 않는지 확인한다.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.agent_run.entities import AgentRunStep
from src.domain.agent_run.value_objects import NodeType, RunId, StepStatus
from src.infrastructure.persistence.models.agent_run import AgentRunStepModel
from src.infrastructure.persistence.repositories.agent_run_repository import (
    SqlAlchemyAgentRunRepository,
)

RUN_ID = "11111111-1111-1111-1111-111111111111"
NOW = datetime(2026, 10, 6, 7, 32, 16, tzinfo=timezone.utc)


def _session() -> MagicMock:
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


def _step(**overrides) -> AgentRunStep:
    base = dict(
        id="child-1", run_id=RunId(RUN_ID), step_index=3, node_name="supervisor",
        node_type=NodeType.SUPERVISOR, llm_model_id=None, status=StepStatus.STARTED,
        input_summary=None, output_summary=None, started_at=NOW, ended_at=None,
        latency_ms=None, error_text=None,
    )
    base.update(overrides)
    return AgentRunStep(**base)


def _row(**overrides) -> AgentRunStepModel:
    base = dict(
        id="child-1", run_id=RUN_ID, step_index=3, node_name="supervisor",
        node_type="SUPERVISOR", llm_model_id=None, status="SUCCESS",
        input_summary=None, output_summary=None, started_at=NOW.replace(tzinfo=None),
        ended_at=None, latency_ms=12, error_text=None,
    )
    base.update(overrides)
    return AgentRunStepModel(**base)


class TestEntityDefaults:
    def test_계층_미지정이면_최상위(self):
        step = _step()
        assert step.parent_step_id is None
        assert step.depth == 0


class TestSaveStep:
    @pytest.mark.asyncio
    async def test_계층_컬럼이_ORM_행에_실린다(self):
        session = _session()
        await SqlAlchemyAgentRunRepository(session).save_step(
            _step(parent_step_id="wrapper-1", depth=1)
        )
        row = session.add.call_args[0][0]
        assert row.parent_step_id == "wrapper-1"
        assert row.depth == 1

    @pytest.mark.asyncio
    async def test_최상위_step은_NULL과_0(self):
        session = _session()
        await SqlAlchemyAgentRunRepository(session).save_step(_step())
        row = session.add.call_args[0][0]
        assert row.parent_step_id is None
        assert row.depth == 0


class TestStepToDomain:
    def test_계층_컬럼을_도메인으로_매핑(self):
        repo = SqlAlchemyAgentRunRepository(_session())
        domain = repo._step_to_domain(_row(parent_step_id="wrapper-1", depth=2))
        assert domain.parent_step_id == "wrapper-1"
        assert domain.depth == 2

    def test_과거_행은_None과_0으로_읽힌다(self):
        """SC-6 — V079 이전 행(컬럼 NULL)도 평면 최상위로 읽힌다."""
        repo = SqlAlchemyAgentRunRepository(_session())
        domain = repo._step_to_domain(_row(parent_step_id=None, depth=None))
        assert domain.parent_step_id is None
        assert domain.depth == 0


class TestUpdateStep:
    @pytest.mark.asyncio
    async def test_update는_계층을_덮어쓰지_않는다(self):
        session = _session()
        row = _row(parent_step_id="wrapper-1", depth=1)
        result = MagicMock()
        result.scalar_one.return_value = row
        session.execute.return_value = result

        await SqlAlchemyAgentRunRepository(session).update_step(
            _step(status=StepStatus.SUCCESS, latency_ms=40)
        )

        assert row.parent_step_id == "wrapper-1"
        assert row.depth == 1
        assert row.latency_ms == 40


class TestOrmComments:
    def test_신규_컬럼에_comment가_있다(self):
        cols = AgentRunStepModel.__table__.columns
        assert cols["parent_step_id"].comment
        assert cols["depth"].comment
