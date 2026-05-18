"""TestsetUseCase 단위 테스트."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.application.ragas.schemas import TestsetUploadRequest
from src.application.ragas.testset_use_case import TestsetUseCase


@pytest.fixture
def mock_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_logger() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def use_case(mock_repo, mock_logger) -> TestsetUseCase:
    return TestsetUseCase(repository=mock_repo, logger=mock_logger)


class TestCreate:
    @pytest.mark.asyncio
    async def test_creates_testset(self, use_case, mock_repo) -> None:
        request = TestsetUploadRequest(
            name="대출 평가셋",
            description="대출 관련 질문 10개",
            cases=[{"question": "q1", "ground_truth": "a1"}],
        )
        response = await use_case.create(request, "req-1")

        assert response.name == "대출 평가셋"
        assert response.case_count == 1
        assert response.id is not None
        mock_repo.save_testset.assert_called_once()


class TestListAll:
    @pytest.mark.asyncio
    async def test_returns_list(self, use_case, mock_repo) -> None:
        mock_repo.list_testsets = AsyncMock(
            return_value=(
                [
                    {
                        "id": "ts-1",
                        "name": "테스트셋1",
                        "description": "desc",
                        "case_count": 5,
                        "created_at": datetime(2026, 5, 13, tzinfo=timezone.utc),
                    }
                ],
                1,
            )
        )
        items, total = await use_case.list_all(20, 0, "req-1")
        assert total == 1
        assert items[0].name == "테스트셋1"


class TestGetDetail:
    @pytest.mark.asyncio
    async def test_returns_detail(self, use_case, mock_repo) -> None:
        mock_repo.get_testset = AsyncMock(
            return_value={
                "id": "ts-1",
                "name": "테스트셋1",
                "description": "desc",
                "case_count": 5,
                "created_at": datetime(2026, 5, 13, tzinfo=timezone.utc),
            }
        )
        detail = await use_case.get_detail("ts-1", "req-1")
        assert detail is not None
        assert detail.id == "ts-1"

    @pytest.mark.asyncio
    async def test_returns_none(self, use_case, mock_repo) -> None:
        mock_repo.get_testset = AsyncMock(return_value=None)
        assert await use_case.get_detail("nonexist", "req-1") is None


class TestDelete:
    @pytest.mark.asyncio
    async def test_delegates(self, use_case, mock_repo) -> None:
        mock_repo.delete_testset = AsyncMock(return_value=True)
        assert await use_case.delete("ts-1", "req-1") is True
