"""AdminEvalUseCase 단위 테스트."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.application.ragas.admin_eval_use_case import AdminEvalUseCase
from src.domain.ragas.entities import EvaluationResult, EvaluationRun


@pytest.fixture
def mock_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_logger() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def use_case(mock_repo, mock_logger) -> AdminEvalUseCase:
    return AdminEvalUseCase(repository=mock_repo, logger=mock_logger)


def _make_run(**overrides) -> EvaluationRun:
    defaults = dict(
        id="run-1",
        eval_type="batch",
        target_type="rag",
        status="completed",
        total_cases=5,
        created_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
        completed_at=datetime(2026, 5, 18, 1, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return EvaluationRun(**defaults)


def _make_result(**overrides) -> EvaluationResult:
    defaults = dict(
        id="res-1",
        run_id="run-1",
        question="RAG란?",
        answer="검색 증강 생성",
        contexts=["ctx1"],
        metrics={"faithfulness": 0.9, "answer_relevancy": 0.8},
        created_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return EvaluationResult(**defaults)


class TestGetDashboardStats:
    @pytest.mark.asyncio
    async def test_returns_stats_with_recent_runs(self, use_case, mock_repo) -> None:
        mock_repo.get_dashboard_stats = AsyncMock(return_value={
            "total_runs": 42,
            "status_counts": {"completed": 38, "failed": 3, "pending": 1},
            "target_type_counts": {"rag": 30, "agent": 10, "retrieval": 2},
            "avg_metrics": {"faithfulness": 0.82},
            "recent_runs": [_make_run()],
        })
        mock_repo.get_run_summary = AsyncMock(
            return_value={"faithfulness": 0.85}
        )

        result = await use_case.get_dashboard_stats(5, "req-1")

        assert result.total_runs == 42
        assert result.status_counts["completed"] == 38
        assert result.target_type_counts["rag"] == 30
        assert result.avg_metrics["faithfulness"] == 0.82
        assert len(result.recent_runs) == 1
        assert result.recent_runs[0].summary["faithfulness"] == 0.85

    @pytest.mark.asyncio
    async def test_empty_db_returns_zero(self, use_case, mock_repo) -> None:
        mock_repo.get_dashboard_stats = AsyncMock(return_value={
            "total_runs": 0,
            "status_counts": {},
            "target_type_counts": {},
            "avg_metrics": {},
            "recent_runs": [],
        })

        result = await use_case.get_dashboard_stats(5, "req-1")

        assert result.total_runs == 0
        assert result.recent_runs == []


class TestListRunsWithSummary:
    @pytest.mark.asyncio
    async def test_returns_filtered_list(self, use_case, mock_repo) -> None:
        mock_repo.list_runs_with_summary = AsyncMock(return_value=(
            [
                {
                    "id": "run-1", "eval_type": "batch", "target_type": "rag",
                    "status": "completed", "total_cases": 5,
                    "created_at": datetime(2026, 5, 18, tzinfo=timezone.utc),
                    "completed_at": datetime(2026, 5, 18, 1, tzinfo=timezone.utc),
                    "summary": {"faithfulness": 0.85},
                },
            ],
            1,
        ))

        items, total = await use_case.list_runs_with_summary(
            "rag", None, "completed", 20, 0, "req-1"
        )

        assert total == 1
        assert items[0].id == "run-1"
        assert items[0].summary["faithfulness"] == 0.85
        mock_repo.list_runs_with_summary.assert_called_once_with(
            "rag", None, "completed", 20, 0, "req-1"
        )


class TestGetRunWithResults:
    @pytest.mark.asyncio
    async def test_returns_run_with_results(self, use_case, mock_repo) -> None:
        mock_repo.get_run = AsyncMock(return_value=_make_run())
        mock_repo.get_run_summary = AsyncMock(
            return_value={"faithfulness": 0.85}
        )
        mock_repo.get_results_by_run = AsyncMock(
            return_value=([_make_result()], 1)
        )

        result = await use_case.get_run_with_results("run-1", "req-1")

        assert result is not None
        assert result.id == "run-1"
        assert result.summary["faithfulness"] == 0.85
        assert result.results_total == 1
        assert result.results[0].question == "RAG란?"
        assert result.results[0].contexts == ["ctx1"]

    @pytest.mark.asyncio
    async def test_returns_none_for_missing(self, use_case, mock_repo) -> None:
        mock_repo.get_run = AsyncMock(return_value=None)

        result = await use_case.get_run_with_results("nonexist", "req-1")

        assert result is None


class TestListTestsets:
    @pytest.mark.asyncio
    async def test_delegates_to_repo(self, use_case, mock_repo) -> None:
        testset = {
            "id": "ts-1", "name": "테스트셋1",
            "description": "설명", "cases": [],
            "case_count": 10,
            "created_at": datetime(2026, 5, 18, tzinfo=timezone.utc),
        }
        mock_repo.list_testsets = AsyncMock(return_value=([testset], 1))

        items, total = await use_case.list_testsets(20, 0, "req-1")

        assert total == 1
        assert items[0]["name"] == "테스트셋1"
