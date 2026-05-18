"""RealtimeEvaluationUseCase 단위 테스트."""
from unittest.mock import AsyncMock

import pytest

from src.application.ragas.realtime_eval_use_case import RealtimeEvaluationUseCase
from src.application.ragas.schemas import RealtimeEvalRequest


@pytest.fixture
def mock_repo() -> AsyncMock:
    repo = AsyncMock()
    return repo


@pytest.fixture
def mock_evaluator() -> AsyncMock:
    evaluator = AsyncMock()
    evaluator.evaluate = AsyncMock(
        return_value={"faithfulness": 0.9, "answer_relevancy": 0.85}
    )
    return evaluator


@pytest.fixture
def mock_logger() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def use_case(mock_repo, mock_evaluator, mock_logger) -> RealtimeEvaluationUseCase:
    return RealtimeEvaluationUseCase(
        repository=mock_repo,
        evaluator=mock_evaluator,
        logger=mock_logger,
    )


class TestExecute:
    @pytest.mark.asyncio
    async def test_evaluates_and_saves(self, use_case, mock_repo, mock_evaluator) -> None:
        request = RealtimeEvalRequest(
            question="대출 한도?",
            answer="최대 5억원입니다.",
            contexts=["문서1"],
        )
        response = await use_case.execute(request, "req-1")

        assert response.scores["faithfulness"] == 0.9
        assert response.scores["answer_relevancy"] == 0.85
        assert response.result_id is not None
        mock_repo.save_run.assert_called_once()
        mock_repo.save_result.assert_called_once()
        mock_evaluator.evaluate.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_marked_completed(self, use_case, mock_repo) -> None:
        request = RealtimeEvalRequest(
            question="q",
            answer="a",
            contexts=["c"],
        )
        await use_case.execute(request, "req-1")

        update_call = mock_repo.update_run.call_args
        run = update_call[0][0]
        assert run.status == "completed"
        assert run.completed_at is not None

    @pytest.mark.asyncio
    async def test_custom_metrics(self, use_case, mock_evaluator) -> None:
        request = RealtimeEvalRequest(
            question="q",
            answer="a",
            contexts=["c"],
            metrics=["faithfulness"],
        )
        await use_case.execute(request, "req-1")

        call_kwargs = mock_evaluator.evaluate.call_args[1]
        assert call_kwargs["metrics"] == ["faithfulness"]
