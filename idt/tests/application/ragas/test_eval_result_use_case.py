"""EvalResultUseCase 단위 테스트."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.application.ragas.eval_result_use_case import EvalResultUseCase
from src.domain.ragas.entities import EvaluationResult, EvaluationRun


@pytest.fixture
def mock_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_logger() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def use_case(mock_repo, mock_logger) -> EvalResultUseCase:
    return EvalResultUseCase(repository=mock_repo, logger=mock_logger)


def _make_run(**overrides) -> EvaluationRun:
    defaults = dict(
        id="run-1",
        eval_type="batch",
        target_type="rag",
        status="completed",
        total_cases=5,
        created_at=datetime(2026, 5, 13, tzinfo=timezone.utc),
        completed_at=datetime(2026, 5, 13, 1, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return EvaluationRun(**defaults)


class TestGetRunDetail:
    @pytest.mark.asyncio
    async def test_returns_detail_with_summary(self, use_case, mock_repo) -> None:
        mock_repo.get_run = AsyncMock(return_value=_make_run())
        mock_repo.get_run_summary = AsyncMock(
            return_value={"faithfulness": 0.85, "answer_relevancy": 0.9}
        )

        detail = await use_case.get_run_detail("run-1", "req-1")
        assert detail is not None
        assert detail.id == "run-1"
        assert detail.summary["faithfulness"] == 0.85

    @pytest.mark.asyncio
    async def test_returns_none_for_missing(self, use_case, mock_repo) -> None:
        mock_repo.get_run = AsyncMock(return_value=None)
        detail = await use_case.get_run_detail("nonexist", "req-1")
        assert detail is None


class TestListRuns:
    @pytest.mark.asyncio
    async def test_returns_list_with_total(self, use_case, mock_repo) -> None:
        mock_repo.list_runs = AsyncMock(
            return_value=([_make_run(), _make_run(id="run-2")], 2)
        )
        items, total = await use_case.list_runs(None, None, 20, 0, "req-1")
        assert total == 2
        assert len(items) == 2


class TestGetResults:
    @pytest.mark.asyncio
    async def test_returns_items(self, use_case, mock_repo) -> None:
        result = EvaluationResult(
            id="res-1",
            run_id="run-1",
            question="q",
            answer="a",
            contexts=["c"],
            metrics={"faithfulness": 0.9},
            created_at=datetime(2026, 5, 13, tzinfo=timezone.utc),
        )
        mock_repo.get_results_by_run = AsyncMock(return_value=([result], 1))

        items, total = await use_case.get_results("run-1", 20, 0, "req-1")
        assert total == 1
        assert items[0].scores["faithfulness"] == 0.9


class TestDeleteRun:
    @pytest.mark.asyncio
    async def test_delegates_to_repo(self, use_case, mock_repo) -> None:
        mock_repo.delete_run = AsyncMock(return_value=True)
        assert await use_case.delete_run("run-1", "req-1") is True
