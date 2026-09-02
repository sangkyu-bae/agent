"""CreateSweepUseCase 검증.

Design Ref: FR-03/FR-04 — 스윕 1건 + 모델 수만큼의 evaluation_run 생성.
Design Ref: §6.1 — 비활성/미존재 모델은 실행 전에 걸러낸다.
Design Ref: D9 — temperature는 항상 0으로 박제된다.
"""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.eval_sweep.schemas import CreateSweepRequest
from src.application.eval_sweep.use_cases import CreateSweepUseCase


def _model(model_id, active=True, in_price="0.001", out_price="0.002"):
    m = MagicMock()
    m.id = model_id
    m.display_name = f"name-{model_id}"
    m.is_active = active
    m.input_price_per_1k_usd = Decimal(in_price)
    m.output_price_per_1k_usd = Decimal(out_price)
    return m


def _make(models=None, cases=3):
    models = models or {mid: _model(mid) for mid in ("m-1", "m-2", "m-judge")}

    sweep_repo = MagicMock()
    sweep_repo.save = AsyncMock(side_effect=lambda s, rid: s)

    eval_repo = MagicMock()
    eval_repo.get_testset = AsyncMock(
        return_value={
            "id": "ts-1",
            "cases": [{"question": f"q{i}"} for i in range(cases)],
        }
    )
    eval_repo.save_run = AsyncMock(side_effect=lambda run, rid: run)

    llm_repo = MagicMock()
    llm_repo.find_by_id = AsyncMock(side_effect=lambda mid, rid: models.get(mid))

    executor = MagicMock()
    executor.kickoff = MagicMock()

    estimator = MagicMock()
    estimator.execute = AsyncMock(
        return_value=MagicMock(estimated_cost_usd=Decimal("1.5"))
    )

    uc = CreateSweepUseCase(
        sweep_repo=sweep_repo,
        eval_repo=eval_repo,
        llm_model_repo=llm_repo,
        executor=executor,
        estimator=estimator,
        logger=MagicMock(),
    )
    return uc, {"sweep_repo": sweep_repo, "eval_repo": eval_repo, "executor": executor}


def _request(model_ids=("m-1", "m-2"), judge="m-judge", metrics=("answer_relevancy",)):
    return CreateSweepRequest(
        name="스윕",
        agent_id="ag-1",
        testset_id="ts-1",
        model_ids=list(model_ids),
        judge_llm_model_id=judge,
        metrics=list(metrics),
    )


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_creates_one_run_per_model(self):
        uc, mocks = _make()

        resp = await uc.execute(_request(), "req-1", user_id="u-1")

        assert resp.total_runs == 2
        assert mocks["eval_repo"].save_run.await_count == 2

    @pytest.mark.asyncio
    async def test_runs_carry_sweep_and_model_dimension(self):
        """§3.3 — 이 두 컬럼이 매트릭스 집계의 축이다."""
        uc, mocks = _make()

        await uc.execute(_request(), "req-1", user_id="u-1")

        runs = [c.args[0] for c in mocks["eval_repo"].save_run.await_args_list]
        assert {r.llm_model_id for r in runs} == {"m-1", "m-2"}
        assert len({r.sweep_id for r in runs}) == 1
        assert all(r.target_type == "agent" for r in runs)

    @pytest.mark.asyncio
    async def test_temperature_is_pinned_to_zero(self):
        uc, mocks = _make()

        await uc.execute(_request(), "req-1", user_id="u-1")

        sweep = mocks["sweep_repo"].save.await_args.args[0]
        assert sweep.temperature == 0.0

    @pytest.mark.asyncio
    async def test_execution_is_kicked_off_with_persist_disabled(self):
        """D2 — 스윕 실행은 대화 이력을 남기지 않는다."""
        uc, mocks = _make()

        await uc.execute(_request(), "req-1", user_id="u-1")

        config = mocks["executor"].kickoff.call_args.args[3]
        assert config.persist_conversation is False
        assert config.temperature_override == 0.0
        assert config.judge_llm_model == "m-judge"

    @pytest.mark.asyncio
    async def test_owner_is_recorded(self):
        uc, mocks = _make()

        await uc.execute(_request(), "req-1", user_id="u-1")

        assert mocks["sweep_repo"].save.await_args.args[0].user_id == "u-1"


class TestValidation:
    @pytest.mark.asyncio
    async def test_rejects_more_than_five_models(self):
        models = {f"m-{i}": _model(f"m-{i}") for i in range(6)}
        models["m-judge"] = _model("m-judge")
        uc, mocks = _make(models=models)

        with pytest.raises(ValueError, match="최대 5개"):
            await uc.execute(
                _request(model_ids=tuple(f"m-{i}" for i in range(6))), "req-1"
            )

        mocks["executor"].kickoff.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_inactive_model(self):
        models = {
            "m-1": _model("m-1"),
            "m-2": _model("m-2", active=False),
            "m-judge": _model("m-judge"),
        }
        uc, _ = _make(models=models)

        with pytest.raises(ValueError, match="비활성"):
            await uc.execute(_request(), "req-1")

    @pytest.mark.asyncio
    async def test_rejects_unknown_model(self):
        models = {"m-1": _model("m-1"), "m-judge": _model("m-judge")}
        uc, _ = _make(models=models)

        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute(_request(), "req-1")

    @pytest.mark.asyncio
    async def test_rejects_empty_testset(self):
        uc, _ = _make(cases=0)

        with pytest.raises(ValueError, match="케이스"):
            await uc.execute(_request(), "req-1")

    @pytest.mark.asyncio
    async def test_rejects_metric_unsupported_by_agent_target(self):
        """스윕은 agent 대상 전용 — faithfulness는 지원되지 않는다."""
        uc, _ = _make()

        with pytest.raises(ValueError, match="faithfulness"):
            await uc.execute(_request(metrics=("faithfulness",)), "req-1")

    @pytest.mark.asyncio
    async def test_nothing_is_saved_when_validation_fails(self):
        uc, mocks = _make(cases=0)

        with pytest.raises(ValueError):
            await uc.execute(_request(), "req-1")

        mocks["sweep_repo"].save.assert_not_awaited()
        mocks["eval_repo"].save_run.assert_not_awaited()
