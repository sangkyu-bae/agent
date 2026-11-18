"""배치 평가의 보조 검색 opt-in (graph-rag-foundation module-7, Design §11.2-7).

관리자가 요청한 agent 평가만 allow_supplemental=True 로 실행·기록한다.
실행 설정(config JSON)에 남겨 general 전환 근거(그래프 끔/켬 실행 2건)를 구분한다.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.application.ragas.batch_eval_use_case import BatchEvaluationUseCase
from src.application.ragas.schemas import BatchEvalRequest


def _uc():
    repo = AsyncMock()
    executor = MagicMock()
    uc = BatchEvaluationUseCase(
        repository=repo, evaluator=AsyncMock(), logger=MagicMock(), executor=executor
    )
    return uc, repo, executor


def _req(**over):
    base = dict(
        target_type="agent",
        metrics=["answer_relevancy"],
        testcases=[{"question": "q"}],
        agent_id="agent-1",
    )
    base.update(over)
    return BatchEvalRequest(**base)


@pytest.mark.asyncio
async def test_allow_supplemental_is_recorded_and_passed_to_executor():
    uc, repo, executor = _uc()
    await uc.execute(_req(allow_supplemental=True), "r", user_id="1")
    run = repo.save_run.await_args.args[0]
    assert run.config["allow_supplemental"] is True
    assert executor.kickoff.call_args.kwargs["config"].allow_supplemental is True


@pytest.mark.asyncio
async def test_default_run_records_false():
    uc, repo, executor = _uc()
    await uc.execute(_req(), "r", user_id="1")
    assert repo.save_run.await_args.args[0].config["allow_supplemental"] is False
    assert executor.kickoff.call_args.kwargs["config"].allow_supplemental is False


@pytest.mark.asyncio
async def test_allow_supplemental_requires_agent_target():
    uc, *_ = _uc()
    with pytest.raises(ValueError, match="agent"):
        await uc.execute(
            _req(
                target_type="rag",
                agent_id=None,
                collection_name="c",
                metrics=["faithfulness"],
                allow_supplemental=True,
            ),
            "r",
        )
