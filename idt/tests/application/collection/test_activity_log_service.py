from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import ProgrammingError

from src.application.collection.activity_log_service import ActivityLogService
from src.domain.collection.schemas import ActionType, ActivityLogEntry


@pytest.fixture
def mock_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_logger() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(mock_repo: AsyncMock, mock_logger: MagicMock) -> ActivityLogService:
    return ActivityLogService(mock_repo, mock_logger)


class TestLog:
    async def test_success_calls_save(
        self, service: ActivityLogService, mock_repo: AsyncMock
    ) -> None:
        await service.log(
            collection_name="test",
            action=ActionType.CREATE,
            request_id="req-1",
            user_id="u1",
            detail={"key": "val"},
        )
        mock_repo.save.assert_awaited_once_with(
            collection_name="test",
            action=ActionType.CREATE,
            user_id="u1",
            detail={"key": "val"},
            request_id="req-1",
        )

    async def test_failure_swallows_exception(
        self, service: ActivityLogService, mock_repo: AsyncMock, mock_logger: MagicMock
    ) -> None:
        mock_repo.save.side_effect = RuntimeError("db error")
        await service.log(
            collection_name="test",
            action=ActionType.SEARCH,
            request_id="req-1",
        )
        mock_logger.warning.assert_called_once()


class TestGetLogs:
    async def test_returns_logs_and_total(
        self, service: ActivityLogService, mock_repo: AsyncMock
    ) -> None:
        mock_repo.find_all.return_value = []
        mock_repo.count.return_value = 0
        logs, total = await service.get_logs(request_id="req-1", limit=10)
        assert logs == []
        assert total == 0

    async def test_count_excludes_limit_and_offset(
        self, service: ActivityLogService, mock_repo: AsyncMock
    ) -> None:
        mock_repo.find_all.return_value = []
        mock_repo.count.return_value = 42
        logs, total = await service.get_logs(
            request_id="req-1",
            collection_name="test",
            limit=50,
            offset=10,
        )
        mock_repo.find_all.assert_awaited_once_with(
            request_id="req-1",
            collection_name="test",
            limit=50,
            offset=10,
        )
        mock_repo.count.assert_awaited_once_with(
            request_id="req-1",
            collection_name="test",
        )
        assert total == 42

    async def test_table_not_exist_returns_empty(
        self, service: ActivityLogService, mock_repo: AsyncMock, mock_logger: MagicMock
    ) -> None:
        orig = ProgrammingError(
            "SELECT ...", {}, Exception("(1146, \"Table 'idt.collection_activity_log' doesn't exist\")")
        )
        mock_repo.find_all.side_effect = orig
        logs, total = await service.get_logs(request_id="req-1")
        assert logs == []
        assert total == 0
        mock_logger.warning.assert_called_once()


class TestGetCollectionLogs:
    async def test_returns_logs_and_total(
        self, service: ActivityLogService, mock_repo: AsyncMock
    ) -> None:
        mock_repo.find_by_collection.return_value = []
        mock_repo.count.return_value = 0
        logs, total = await service.get_collection_logs("test", "req-1", limit=20)
        mock_repo.find_by_collection.assert_awaited_once_with(
            collection_name="test", request_id="req-1", limit=20, offset=0
        )
        assert logs == []
        assert total == 0

    async def test_table_not_exist_returns_empty(
        self, service: ActivityLogService, mock_repo: AsyncMock, mock_logger: MagicMock
    ) -> None:
        orig = ProgrammingError(
            "SELECT ...", {}, Exception("(1146, \"Table 'idt.collection_activity_log' doesn't exist\")")
        )
        mock_repo.find_by_collection.side_effect = orig
        logs, total = await service.get_collection_logs("test", "req-1")
        assert logs == []
        assert total == 0
        mock_logger.warning.assert_called_once()
