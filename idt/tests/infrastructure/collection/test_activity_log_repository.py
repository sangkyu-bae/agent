from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.collection.schemas import ActionType, ActivityLogEntry
from src.infrastructure.collection.activity_log_repository import (
    ActivityLogRepository,
)
from src.infrastructure.collection.models import CollectionActivityLogModel


@pytest.fixture
def mock_session() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_logger() -> MagicMock:
    return MagicMock()


@pytest.fixture
def repo(mock_session: AsyncMock, mock_logger: MagicMock) -> ActivityLogRepository:
    return ActivityLogRepository(mock_session, mock_logger)


class TestSave:
    async def test_adds_and_flushes(
        self, repo: ActivityLogRepository, mock_session: AsyncMock
    ) -> None:
        await repo.save(
            collection_name="test-col",
            action=ActionType.CREATE,
            user_id="user1",
            detail={"vector_size": 1536},
            request_id="req-1",
        )
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

        model = mock_session.add.call_args[0][0]
        assert isinstance(model, CollectionActivityLogModel)
        assert model.collection_name == "test-col"
        assert model.action == "CREATE"
        assert model.user_id == "user1"


class TestToEntry:
    def test_converts_model_to_domain(self) -> None:
        now = datetime(2026, 4, 21, 10, 0, 0)
        model = CollectionActivityLogModel(
            id=1,
            collection_name="docs",
            action="SEARCH",
            user_id="u1",
            detail={"query": "test"},
            created_at=now,
        )
        entry = ActivityLogRepository._to_entry(model)
        assert entry == ActivityLogEntry(
            id=1,
            collection_name="docs",
            action=ActionType.SEARCH,
            user_id="u1",
            detail={"query": "test"},
            created_at=now,
        )
