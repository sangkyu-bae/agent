"""Tests for KbSearchHistoryUseCase (kb-retrieval-test Design D8)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection_search.search_history_schemas import (
    SearchHistoryEntry,
)


def _make_user() -> User:
    return User(
        email="test@example.com",
        password_hash="hash",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=1,
    )


def _make_entry(id_: int = 1) -> SearchHistoryEntry:
    return SearchHistoryEntry(
        id=id_,
        user_id="1",
        collection_name="col-a",
        query="q",
        bm25_weight=0.5,
        vector_weight=0.5,
        top_k=10,
        result_count=5,
        created_at=datetime(2026, 7, 18),
        kb_id="kb-1",
    )


def _create_use_case(kb_use_case, repo):
    from src.application.knowledge_base.search_history_use_case import (
        KbSearchHistoryUseCase,
    )

    return KbSearchHistoryUseCase(
        kb_use_case=kb_use_case,
        search_history_repo=repo,
        logger=MagicMock(),
    )


class TestKbSearchHistoryUseCase:
    @pytest.mark.asyncio
    async def test_returns_kb_scoped_result(self):
        kb_use_case = AsyncMock()
        repo = AsyncMock()
        repo.find_by_user_and_kb = AsyncMock(
            return_value=([_make_entry()], 1)
        )
        uc = _create_use_case(kb_use_case, repo)

        result = await uc.execute(
            kb_id="kb-1",
            user=_make_user(),
            limit=10,
            offset=0,
            request_id="req-1",
        )

        assert result.kb_id == "kb-1"
        assert result.total == 1
        assert result.histories[0].kb_id == "kb-1"
        kb_use_case.get.assert_awaited_once()
        repo.find_by_user_and_kb.assert_called_once_with(
            user_id="1", kb_id="kb-1", limit=10, offset=0, request_id="req-1"
        )

    @pytest.mark.asyncio
    async def test_permission_error_propagates(self):
        kb_use_case = AsyncMock()
        kb_use_case.get = AsyncMock(
            side_effect=PermissionError("No read access")
        )
        uc = _create_use_case(kb_use_case, AsyncMock())

        with pytest.raises(PermissionError):
            await uc.execute(
                kb_id="kb-1",
                user=_make_user(),
                limit=10,
                offset=0,
                request_id="req-1",
            )

    @pytest.mark.asyncio
    async def test_kb_not_found_propagates(self):
        kb_use_case = AsyncMock()
        kb_use_case.get = AsyncMock(
            side_effect=ValueError("Knowledge base 'kb-x' not found")
        )
        uc = _create_use_case(kb_use_case, AsyncMock())

        with pytest.raises(ValueError, match="not found"):
            await uc.execute(
                kb_id="kb-x",
                user=_make_user(),
                limit=10,
                offset=0,
                request_id="req-1",
            )
