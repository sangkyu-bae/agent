"""Infrastructure 테스트: list_searchable_tree_items (wiki-agentic-navigation D7).

프롬프트 목차용 승인+미만료 경량 조회. WHERE 절은 entity.is_searchable(now)의
SQL 미러 — 컴파일된 쿼리 문자열로 필터·정렬 의미를 고정한다.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.wiki.schemas import WikiTreeItem
from src.infrastructure.wiki.wiki_repository import WikiArticleRepository

NOW = datetime(2026, 7, 23, tzinfo=timezone.utc)


def _repo(session):
    return WikiArticleRepository(
        session=session, logger=MagicMock(),
        embedding=MagicMock(), vector_store=MagicMock(),
        collection_name="wiki_knowledge",
    )


def _row(id="w1", title="제목", path="여신/한도"):
    r = MagicMock()
    r.id = id
    r.title = title
    r.status = "approved"
    r.source_type = "human"
    r.path = path
    r.updated_at = NOW
    return r


def _session_returning(rows):
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    return session


class TestListSearchableTreeItems:

    @pytest.mark.asyncio
    async def test_maps_rows_to_tree_items_in_order(self):
        session = _session_returning([_row("w2"), _row("w1")])
        repo = _repo(session)
        items = await repo.list_searchable_tree_items("agent_1", NOW, "r")
        assert [i.id for i in items] == ["w2", "w1"]
        assert all(isinstance(i, WikiTreeItem) for i in items)
        assert items[0].title == "제목"
        assert items[0].path == "여신/한도"

    @pytest.mark.asyncio
    async def test_empty_returns_empty_list(self):
        repo = _repo(_session_returning([]))
        assert await repo.list_searchable_tree_items("agent_1", NOW, "r") == []

    @pytest.mark.asyncio
    async def test_query_mirrors_is_searchable_and_orders_by_updated_desc(self):
        """SQL 필터가 entity.is_searchable(승인+미만료)의 미러임을 문자열로 고정."""
        session = _session_returning([])
        repo = _repo(session)
        await repo.list_searchable_tree_items("agent_1", NOW, "r")

        stmt = session.execute.await_args.args[0]
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "agent_id" in sql
        assert "'approved'" in sql
        assert "valid_until IS NULL" in sql
        assert "valid_until >" in sql
        assert "ORDER BY" in sql and "updated_at DESC" in sql
        # 본문 미조회(경량) — content 컬럼이 SELECT에 없어야 한다
        assert "content" not in sql.split("FROM")[0]
