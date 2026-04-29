"""Tests for SearchHistoryUseCase."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.collection_search.search_history_schemas import SearchHistoryEntry


def _make_entry(id_: int = 1) -> SearchHistoryEntry:
    return SearchHistoryEntry(
        id=id_,
        user_id="u1",
        collection_name="c",
        query="q",
        bm25_weight=0.5,
        vector_weight=0.5,
        top_k=10,
        result_count=5,
        created_at=datetime(2026, 4, 28),
    )


class TestSearchHistoryUseCaseExecute:
    @pytest.mark.asyncio
    async def test_returns_list_result(self):
        from src.application.collection_search.search_history_use_case import (
            SearchHistoryUseCase,
        )

        repo = AsyncMock()
        repo.find_by_user_and_collection = AsyncMock(
            return_value=([_make_entry()], 1)
        )
        uc = SearchHistoryUseCase(search_history_repo=repo, logger=MagicMock())

        result = await uc.execute(
            user_id="u1",
            collection_name="c",
            limit=20,
            offset=0,
            request_id="req-1",
        )

        assert result.total == 1
        assert len(result.histories) == 1
        assert result.collection_name == "c"

    @pytest.mark.asyncio
    async def test_empty_result(self):
        from src.application.collection_search.search_history_use_case import (
            SearchHistoryUseCase,
        )

        repo = AsyncMock()
        repo.find_by_user_and_collection = AsyncMock(return_value=([], 0))
        uc = SearchHistoryUseCase(search_history_repo=repo, logger=MagicMock())

        result = await uc.execute(
            user_id="u1",
            collection_name="c",
            limit=20,
            offset=0,
            request_id="req-1",
        )

        assert result.total == 0
        assert result.histories == []

    @pytest.mark.asyncio
    async def test_pagination_params_passed(self):
        from src.application.collection_search.search_history_use_case import (
            SearchHistoryUseCase,
        )

        repo = AsyncMock()
        repo.find_by_user_and_collection = AsyncMock(return_value=([], 0))
        uc = SearchHistoryUseCase(search_history_repo=repo, logger=MagicMock())

        result = await uc.execute(
            user_id="u1",
            collection_name="c",
            limit=5,
            offset=10,
            request_id="req-1",
        )

        assert result.limit == 5
        assert result.offset == 10
        repo.find_by_user_and_collection.assert_called_once_with(
            user_id="u1",
            collection_name="c",
            limit=5,
            offset=10,
            request_id="req-1",
        )
