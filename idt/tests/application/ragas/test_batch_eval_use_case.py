"""BatchEvaluationUseCase 단위 테스트."""
from unittest.mock import AsyncMock

import pytest

from src.application.ragas.batch_eval_use_case import BatchEvaluationUseCase
from src.application.ragas.schemas import BatchEvalRequest


@pytest.fixture
def mock_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.save_run = AsyncMock()
    repo.get_run = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_evaluator() -> AsyncMock:
    evaluator = AsyncMock()
    evaluator.evaluate = AsyncMock(return_value={"faithfulness": 0.9})
    return evaluator


@pytest.fixture
def mock_logger() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def use_case(mock_repo, mock_evaluator, mock_logger) -> BatchEvaluationUseCase:
    return BatchEvaluationUseCase(
        repository=mock_repo,
        evaluator=mock_evaluator,
        logger=mock_logger,
    )


class TestExecute:
    @pytest.mark.asyncio
    async def test_creates_run_and_returns_response(self, use_case, mock_repo) -> None:
        request = BatchEvalRequest(
            target_type="rag",
            metrics=["faithfulness"],
            testcases=[{"question": "대출 한도?"}],
        )
        response = await use_case.execute(request, "req-1")

        assert response.status == "pending"
        assert response.total_cases == 1
        assert response.run_id is not None
        mock_repo.save_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_metrics_raises(self, use_case) -> None:
        request = BatchEvalRequest(
            target_type="rag",
            metrics=[],
            testcases=[{"question": "q"}],
        )
        with pytest.raises(ValueError, match="1개 이상"):
            await use_case.execute(request, "req-1")

    @pytest.mark.asyncio
    async def test_empty_testcases_raises(self, use_case) -> None:
        # testset_id도 testcases도 없음 → 배타 검증 위반 (eval-hub A8)
        request = BatchEvalRequest(
            target_type="rag",
            metrics=["faithfulness"],
            testcases=[],
        )
        with pytest.raises(ValueError, match="정확히 하나"):
            await use_case.execute(request, "req-1")

    @pytest.mark.asyncio
    async def test_gt_required_but_missing_raises(self, use_case) -> None:
        request = BatchEvalRequest(
            target_type="rag",
            metrics=["context_recall"],
            testcases=[{"question": "q"}],
        )
        with pytest.raises(ValueError, match="ground_truth"):
            await use_case.execute(request, "req-1")

    @pytest.mark.asyncio
    async def test_sample_ratio_reduces_cases(self, use_case, mock_repo) -> None:
        request = BatchEvalRequest(
            target_type="rag",
            metrics=["faithfulness"],
            testcases=[{"question": f"q{i}"} for i in range(10)],
            sample_ratio=0.3,
        )
        response = await use_case.execute(request, "req-1")
        assert response.total_cases == 3


# 실행(run) 단계는 BatchEvalExecutor로 이관 — tests/application/ragas/test_batch_executor.py 참조
