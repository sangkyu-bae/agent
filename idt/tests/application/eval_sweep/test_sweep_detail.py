"""GetSweepDetailUseCase — 실제 비용(G-1)과 실험 조건(G-2) 노출 검증."""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.eval_sweep.use_cases import GetSweepDetailUseCase
from src.domain.eval_sweep.entity import EvaluationSweep, SweepRow


def _sweep():
    return EvaluationSweep(
        id="sw-1",
        name="스윕",
        agent_id="ag-1",
        testset_id="ts-1",
        judge_llm_model_id="m-judge",
        model_ids=["m-1", "m-2"],
        metrics=["answer_relevancy"],
        total_runs=2,
        estimated_cost_usd=Decimal("1.842000"),
        user_id="u-1",
        created_at=datetime.now(timezone.utc),
    )


def _row(run_id, cost):
    return SweepRow(
        run_id=run_id,
        llm_model_id="m-1",
        status="completed",
        quality={"answer_relevancy": 0.9},
        cost_usd=None if cost is None else Decimal(cost),
        measured_cases=10,
    )


def _make(rows, *, with_context=True, agent_raises=False):
    sweep_repo = MagicMock()
    sweep_repo.get = AsyncMock(return_value=_sweep())
    sweep_repo.get_rows = AsyncMock(return_value=rows)

    llm_repo = MagicMock()
    llm_repo.find_by_id = AsyncMock(return_value=MagicMock(display_name="GPT-4o"))

    agent_repo = eval_repo = None
    if with_context:
        agent_repo = MagicMock()
        agent_repo.find_by_id = AsyncMock(
            side_effect=RuntimeError("DB 끊김") if agent_raises
            else None,
            return_value=None if agent_raises else MagicMock(name_="x"),
        )
        if not agent_raises:
            agent = MagicMock()
            agent.name = "여신심사봇"
            agent_repo.find_by_id = AsyncMock(return_value=agent)
        eval_repo = MagicMock()
        eval_repo.get_testset = AsyncMock(
            return_value={
                "id": "ts-1",
                "name": "여신 골든셋 v3",
                "cases": [{"question": f"q{i}"} for i in range(20)],
            }
        )

    return GetSweepDetailUseCase(
        sweep_repo=sweep_repo,
        llm_model_repo=llm_repo,
        logger=MagicMock(),
        agent_repo=agent_repo,
        eval_repo=eval_repo,
    )


class TestActualCost:
    """G-1 — 실제 지출이 보여야 '싼 모델로 내려도 되는가'를 숫자로 닫을 수 있다."""

    @pytest.mark.asyncio
    async def test_sums_row_costs(self):
        uc = _make([_row("r-1", "1.10"), _row("r-2", "0.06")])

        detail = await uc.execute("sw-1", "req-1", scope_user_id="u-1")

        assert detail.actual_cost_usd == Decimal("1.16")

    @pytest.mark.asyncio
    async def test_ignores_unmeasured_rows(self):
        uc = _make([_row("r-1", "1.10"), _row("r-2", None)])

        detail = await uc.execute("sw-1", "req-1", scope_user_id="u-1")

        assert detail.actual_cost_usd == Decimal("1.10")

    @pytest.mark.asyncio
    async def test_returns_none_when_nothing_measured(self):
        """0원이 아니라 N/A — 측정 실패와 무료 실행을 구분한다 (§3.5)."""
        uc = _make([_row("r-1", None), _row("r-2", None)])

        detail = await uc.execute("sw-1", "req-1", scope_user_id="u-1")

        assert detail.actual_cost_usd is None

    @pytest.mark.asyncio
    async def test_estimate_is_still_available_for_comparison(self):
        uc = _make([_row("r-1", "1.10")])

        detail = await uc.execute("sw-1", "req-1", scope_user_id="u-1")

        assert detail.estimated_cost_usd == Decimal("1.842000")
        assert detail.actual_cost_usd == Decimal("1.10")


class TestExperimentConditions:
    """G-2 — 어떤 조건의 실험이었는지 알아야 재현성 스냅샷이 쓸모를 갖는다."""

    @pytest.mark.asyncio
    async def test_exposes_agent_testset_and_case_count(self):
        uc = _make([_row("r-1", "1.10")])

        detail = await uc.execute("sw-1", "req-1", scope_user_id="u-1")

        assert detail.agent_name == "여신심사봇"
        assert detail.testset_name == "여신 골든셋 v3"
        assert detail.case_count == 20

    @pytest.mark.asyncio
    async def test_works_without_context_repos(self):
        """리포지토리 미주입 시에도 상세 조회는 정상 동작한다."""
        uc = _make([_row("r-1", "1.10")], with_context=False)

        detail = await uc.execute("sw-1", "req-1", scope_user_id="u-1")

        assert detail.agent_name is None
        assert detail.case_count == 0
        assert detail.actual_cost_usd == Decimal("1.10")

    @pytest.mark.asyncio
    async def test_lookup_failure_does_not_break_detail(self):
        """이름은 부가 정보 — 조회가 실패해도 매트릭스는 나와야 한다."""
        uc = _make([_row("r-1", "1.10")])
        uc._agent_repo.find_by_id = AsyncMock(side_effect=RuntimeError("DB 끊김"))

        detail = await uc.execute("sw-1", "req-1", scope_user_id="u-1")

        assert detail.agent_name is None
        assert len(detail.rows) == 1
