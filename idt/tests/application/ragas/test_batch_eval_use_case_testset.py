"""BatchEvaluationUseCase — testset_id 실행·소유권·메트릭 검증 (eval-hub Design A8)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.ragas.batch_eval_use_case import BatchEvaluationUseCase
from src.application.ragas.schemas import BatchEvalRequest


def _repo(testset=None):
    repo = MagicMock()
    repo.get_testset = AsyncMock(return_value=testset)
    repo.save_run = AsyncMock(side_effect=lambda run, rid: run)
    return repo


def _uc(repo, executor=None):
    return BatchEvaluationUseCase(
        repository=repo,
        evaluator=MagicMock(),
        logger=MagicMock(),
        executor=executor,
    )


def _testset_row(user_id="7"):
    return {
        "id": "ts-1", "name": "셋", "description": "", "user_id": user_id,
        "cases": [
            {"question": "q1", "ground_truth": "a1"},
            {"question": "q2", "ground_truth": "a2"},
        ],
        "case_count": 2, "created_at": datetime.now(timezone.utc),
    }


def _request(**over):
    base = dict(
        target_type="rag",
        metrics=["faithfulness"],
        testcases=[],
        testset_id="ts-1",
        collection_name="col-1",
    )
    base.update(over)
    return BatchEvalRequest(**base)


class TestTestsetIdExecution:
    @pytest.mark.asyncio
    async def test_testset_id로_케이스_로드_및_run_저장(self):
        repo = _repo(_testset_row())
        uc = _uc(repo)

        resp = await uc.execute(_request(), "rid", user_id="7", scope_user_id="7")

        assert resp.total_cases == 2
        saved_run = repo.save_run.await_args.args[0]
        assert saved_run.user_id == "7"
        assert saved_run.config["testset_id"] == "ts-1"

    @pytest.mark.asyncio
    async def test_둘_다_제공시_ValueError(self):
        uc = _uc(_repo(_testset_row()))
        with pytest.raises(ValueError):
            await uc.execute(
                _request(testcases=[{"question": "q"}]),
                "rid", user_id="7", scope_user_id="7",
            )

    @pytest.mark.asyncio
    async def test_둘_다_없으면_ValueError(self):
        uc = _uc(_repo())
        with pytest.raises(ValueError):
            await uc.execute(
                _request(testset_id=None), "rid", user_id="7", scope_user_id="7"
            )

    @pytest.mark.asyncio
    async def test_타인_테스트셋_찾을수없음(self):
        repo = _repo(_testset_row(user_id="99"))
        uc = _uc(repo)
        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute(_request(), "rid", user_id="7", scope_user_id="7")

    @pytest.mark.asyncio
    async def test_admin은_타인_테스트셋_실행_가능(self):
        repo = _repo(_testset_row(user_id="99"))
        uc = _uc(repo)
        resp = await uc.execute(_request(), "rid", user_id="1", scope_user_id=None)
        assert resp.total_cases == 2

    @pytest.mark.asyncio
    async def test_인라인_testcases_하위호환(self):
        repo = _repo()
        uc = _uc(repo)
        resp = await uc.execute(
            _request(testset_id=None, testcases=[{"question": "q"}]),
            "rid", user_id="7", scope_user_id="7",
        )
        assert resp.total_cases == 1


class TestMetricTargetValidation:
    @pytest.mark.asyncio
    async def test_대상에_안맞는_메트릭_ValueError(self):
        uc = _uc(_repo(_testset_row()))
        with pytest.raises(ValueError, match="지원하지 않"):
            await uc.execute(
                _request(target_type="retrieval", metrics=["faithfulness"]),
                "rid", user_id="7", scope_user_id="7",
            )

    @pytest.mark.asyncio
    async def test_retrieval_대상_메트릭_허용(self):
        uc = _uc(_repo(_testset_row()))
        resp = await uc.execute(
            _request(target_type="retrieval", metrics=["hit_rate", "context_recall"]),
            "rid", user_id="7", scope_user_id="7",
        )
        assert resp.status == "pending"


class TestExecutorKickoff:
    @pytest.mark.asyncio
    async def test_실행기_킥오프_호출(self):
        executor = MagicMock()
        repo = _repo(_testset_row())
        uc = _uc(repo, executor=executor)

        await uc.execute(_request(), "rid", user_id="7", scope_user_id="7")

        assert executor.kickoff.call_count == 1
        kwargs = executor.kickoff.call_args.kwargs
        assert kwargs["target_type"] == "rag"
        assert kwargs["user_id"] == "7"
        assert len(kwargs["testcases"]) == 2

    @pytest.mark.asyncio
    async def test_실행기_없어도_등록은_성공(self):
        uc = _uc(_repo(_testset_row()), executor=None)
        resp = await uc.execute(_request(), "rid", user_id="7", scope_user_id="7")
        assert resp.status == "pending"
