"""SweepRepository 통합 테스트 (SQLite + 실제 세션).

Design §4.2 / D8·D10·D11 검증:
- 모델별 4축 집계 (evaluation_run ⋈ evaluation_result ⋈ ai_run)
- ai_run 조인 실패 시 비용·지연만 N/A로 낙하 (D11)
- 관리자 대시보드가 스윕 run을 제외하는지 (D8 / L1-9)

Gap 분석 §5에서 "집계 SQL 미커버"로 표시했던 영역을 덮는다.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from typing import AsyncGenerator
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.domain.eval_sweep.entity import EvaluationSweep
from src.infrastructure.eval_sweep.repository import SweepRepository
from src.infrastructure.persistence.models.agent_run import AgentRunModel
from src.infrastructure.persistence.models.base import Base
from src.infrastructure.ragas.models import EvaluationResultModel, EvaluationRunModel
from src.infrastructure.ragas.repository import EvaluationRepository

NOW = datetime(2026, 9, 2, tzinfo=timezone.utc)


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp.name}", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as s:
            async with s.begin():
                yield s
    finally:
        await engine.dispose()
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _repo(session) -> SweepRepository:
    return SweepRepository(session, MagicMock())


def _sweep(sweep_id="sw-1", user_id="u-1") -> EvaluationSweep:
    return EvaluationSweep(
        id=sweep_id, name="스윕", agent_id="ag-1", testset_id="ts-1",
        judge_llm_model_id="m-judge", model_ids=["m-1", "m-2"],
        metrics=["answer_relevancy"], total_runs=2,
        estimated_cost_usd=Decimal("1.5"), user_id=user_id, created_at=NOW,
    )


def _run(session, run_id, *, sweep_id=None, model_id=None, total_cases=2,
         status="completed"):
    session.add(EvaluationRunModel(
        id=run_id, eval_type="batch", target_type="agent", target_id="ag-1",
        sweep_id=sweep_id, llm_model_id=model_id, user_id="u-1",
        status=status, total_cases=total_cases, config={}, created_at=NOW,
    ))


def _result(session, result_id, run_id, *, metrics, ai_run_id=None):
    session.add(EvaluationResultModel(
        id=result_id, run_id=run_id, ai_run_id=ai_run_id,
        question="q", answer="a", contexts=[], metrics=metrics, created_at=NOW,
    ))


def _ai_run(session, run_id, *, cost, latency):
    session.add(AgentRunModel(
        id=run_id, conversation_id="c", user_id="u-1", agent_id="ag-1",
        status="SUCCESS", langgraph_thread_id="t",
        prompt_tokens=100, completion_tokens=50, total_tokens=150,
        total_cost_usd=Decimal(cost), llm_call_count=1,
        started_at=NOW, latency_ms=latency,
    ))


class TestPersistence:
    @pytest.mark.asyncio
    async def test_saves_and_reads_back_snapshot(self, session):
        repo = _repo(session)
        await repo.save(_sweep(), "req-1")

        loaded = await repo.get("sw-1", "req-1")

        assert loaded.model_ids == ["m-1", "m-2"]
        assert loaded.metrics == ["answer_relevancy"]
        assert loaded.temperature == 0.0
        assert loaded.estimated_cost_usd == Decimal("1.5")

    @pytest.mark.asyncio
    async def test_list_scopes_to_owner(self, session):
        repo = _repo(session)
        await repo.save(_sweep("sw-1", user_id="u-1"), "req-1")
        await repo.save(_sweep("sw-2", user_id="u-2"), "req-1")

        mine, total = await repo.list_by_user("u-1", 20, 0, "req-1")

        assert total == 1
        assert mine[0].id == "sw-1"

    @pytest.mark.asyncio
    async def test_admin_sees_all(self, session):
        repo = _repo(session)
        await repo.save(_sweep("sw-1", user_id="u-1"), "req-1")
        await repo.save(_sweep("sw-2", user_id="u-2"), "req-1")

        _, total = await repo.list_by_user(None, 20, 0, "req-1")

        assert total == 2


class TestAggregation:
    """§4.2 rows[] — 모델별 4축."""

    @pytest.mark.asyncio
    async def test_aggregates_quality_cost_latency_and_tools(self, session):
        repo = _repo(session)
        await repo.save(_sweep(), "req-1")
        _run(session, "r-1", sweep_id="sw-1", model_id="m-1")
        _ai_run(session, "ar-1", cost="0.50", latency=1000)
        _ai_run(session, "ar-2", cost="0.30", latency=3000)
        _result(session, "res-1", "r-1",
                metrics={"answer_relevancy": 0.9, "tool_f1": 1.0}, ai_run_id="ar-1")
        _result(session, "res-2", "r-1",
                metrics={"answer_relevancy": 0.7, "tool_f1": 0.5}, ai_run_id="ar-2")
        await session.flush()

        rows = await repo.get_rows("sw-1", "req-1")

        assert len(rows) == 1
        row = rows[0]
        assert row.llm_model_id == "m-1"
        assert row.quality["answer_relevancy"] == pytest.approx(0.8)
        assert row.cost_usd == Decimal("0.80")
        assert row.tool_f1 == pytest.approx(0.75)
        assert row.measured_cases == 2

    @pytest.mark.asyncio
    async def test_none_metrics_are_excluded_from_average(self, session):
        """§3.5 — N/A는 분모에서 빠진다. 0으로 세면 평균이 왜곡된다."""
        repo = _repo(session)
        await repo.save(_sweep(), "req-1")
        _run(session, "r-1", sweep_id="sw-1", model_id="m-1")
        _result(session, "res-1", "r-1", metrics={"answer_relevancy": 0.9})
        _result(session, "res-2", "r-1", metrics={"answer_relevancy": None})
        await session.flush()

        rows = await repo.get_rows("sw-1", "req-1")

        assert rows[0].quality["answer_relevancy"] == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_missing_ai_run_degrades_only_cost_and_latency(self, session):
        """D11 — 관측이 없어도 품질 지표는 살아야 한다."""
        repo = _repo(session)
        await repo.save(_sweep(), "req-1")
        _run(session, "r-1", sweep_id="sw-1", model_id="m-1")
        _result(session, "res-1", "r-1",
                metrics={"answer_relevancy": 0.9}, ai_run_id=None)
        await session.flush()

        row = (await repo.get_rows("sw-1", "req-1"))[0]

        assert row.cost_usd is None
        assert row.latency_p50_ms is None
        assert row.quality["answer_relevancy"] == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_dangling_ai_run_id_does_not_raise(self, session):
        """D11 — ai_run이 보존정책으로 선삭제돼도 조회가 깨지면 안 된다."""
        repo = _repo(session)
        await repo.save(_sweep(), "req-1")
        _run(session, "r-1", sweep_id="sw-1", model_id="m-1")
        _result(session, "res-1", "r-1",
                metrics={"answer_relevancy": 0.9}, ai_run_id="사라진-run")
        await session.flush()

        row = (await repo.get_rows("sw-1", "req-1"))[0]

        assert row.cost_usd is None
        assert row.quality["answer_relevancy"] == pytest.approx(0.9)

    @pytest.mark.asyncio
    async def test_failed_run_reports_failed_cases(self, session):
        repo = _repo(session)
        await repo.save(_sweep(), "req-1")
        _run(session, "r-1", sweep_id="sw-1", model_id="m-1",
             total_cases=5, status="failed")
        await session.flush()

        row = (await repo.get_rows("sw-1", "req-1"))[0]

        assert row.status == "failed"
        assert row.measured_cases == 0
        assert row.failed_cases == 5

    @pytest.mark.asyncio
    async def test_only_rows_of_this_sweep_are_returned(self, session):
        repo = _repo(session)
        await repo.save(_sweep("sw-1"), "req-1")
        await repo.save(_sweep("sw-2"), "req-1")
        _run(session, "r-1", sweep_id="sw-1", model_id="m-1")
        _run(session, "r-2", sweep_id="sw-2", model_id="m-2")
        await session.flush()

        rows = await repo.get_rows("sw-1", "req-1")

        assert [r.run_id for r in rows] == ["r-1"]


class TestDashboardExclusion:
    """L1-9 / D8 — 스윕 run은 운영 품질 통계에서 빠져야 한다."""

    @pytest.mark.asyncio
    async def test_sweep_runs_are_excluded_from_dashboard_stats(self, session):
        sweep_repo = _repo(session)
        await sweep_repo.save(_sweep(), "req-1")
        # 단독 실행 1건 + 스윕 소속 2건
        _run(session, "solo", sweep_id=None, model_id=None)
        _run(session, "sw-run-1", sweep_id="sw-1", model_id="m-1")
        _run(session, "sw-run-2", sweep_id="sw-1", model_id="m-2")
        _result(session, "res-solo", "solo", metrics={"answer_relevancy": 0.5})
        _result(session, "res-sw", "sw-run-1", metrics={"answer_relevancy": 1.0})
        await session.flush()

        stats = await EvaluationRepository(session, MagicMock()).get_dashboard_stats(
            10, "req-1"
        )

        assert stats["total_runs"] == 1
        assert [r.id for r in stats["recent_runs"]] == ["solo"]
        # 스윕의 만점(1.0)이 섞였다면 평균이 0.5보다 높아진다
        assert stats["avg_metrics"]["answer_relevancy"] == pytest.approx(0.5)


class TestRunListExclusion:
    """G-11 — 스윕 하위 run이 사용자 '평가 실행' 목록을 덮으면 안 된다.

    모델 5개 스윕 1회 = 목록에 5행. 스윕은 전용 섹션에서 보므로 여기서는 뺀다.
    """

    @pytest.mark.asyncio
    async def test_sweep_runs_are_excluded_from_run_list(self, session):
        sweep_repo = _repo(session)
        await sweep_repo.save(_sweep(), "req-1")
        _run(session, "solo", sweep_id=None)
        for i in range(5):
            _run(session, f"sw-run-{i}", sweep_id="sw-1", model_id=f"m-{i}")
        await session.flush()

        runs, total = await EvaluationRepository(session, MagicMock()).list_runs(
            None, None, 20, 0, "req-1", user_id="u-1"
        )

        assert total == 1
        assert [r.id for r in runs] == ["solo"]

    @pytest.mark.asyncio
    async def test_standalone_runs_are_untouched(self, session):
        """기능 도입 이전 의미를 그대로 복원해야 한다 — 기존 run은 전부 보인다."""
        _run(session, "solo-1", sweep_id=None)
        _run(session, "solo-2", sweep_id=None)
        await session.flush()

        _, total = await EvaluationRepository(session, MagicMock()).list_runs(
            None, None, 20, 0, "req-1", user_id="u-1"
        )

        assert total == 2

    @pytest.mark.asyncio
    async def test_run_carries_sweep_identity_when_read_directly(self, session):
        """G-10 — 목록에서 빠져도 단건 조회로는 소속이 드러나야 한다."""
        sweep_repo = _repo(session)
        await sweep_repo.save(_sweep(), "req-1")
        _run(session, "sw-run-1", sweep_id="sw-1", model_id="m-1")
        await session.flush()

        run = await EvaluationRepository(session, MagicMock()).get_run(
            "sw-run-1", "req-1"
        )

        assert run.sweep_id == "sw-1"
        assert run.llm_model_id == "m-1"
