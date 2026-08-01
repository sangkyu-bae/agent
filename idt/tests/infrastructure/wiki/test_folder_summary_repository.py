"""Infrastructure 테스트: WikiFolderSummaryRepository (wiki-folder-summaries D1).

컴파일된 SQL 문자열로 필터 의미를 고정한다 (test_wiki_repository_toc 관례).
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.wiki.entity import WikiFolderSummary
from src.infrastructure.wiki.folder_summary_repository import (
    MySQLWikiFolderSummaryRepository,
)

NOW = datetime(2026, 7, 25)


def _repo(session):
    return MySQLWikiFolderSummaryRepository(session=session, logger=MagicMock())


def _row(path="여신", summary="요약", count=2):
    r = MagicMock()
    r.id = f"f-{path}"
    r.agent_id = "a1"
    r.path = path
    r.summary = summary
    r.article_count = count
    r.updated_at = NOW
    return r


def _session_returning(rows):
    session = AsyncMock()
    result = MagicMock()
    result.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    return session


class TestListByAgent:

    @pytest.mark.asyncio
    async def test_maps_rows_to_entities(self):
        session = _session_returning([_row("여신"), _row("여신/한도")])
        items = await _repo(session).list_by_agent("a1", "r")
        assert [i.path for i in items] == ["여신", "여신/한도"]
        assert all(isinstance(i, WikiFolderSummary) for i in items)
        assert items[0].summary == "요약"

    @pytest.mark.asyncio
    async def test_query_filters_agent_and_orders_by_path(self):
        session = _session_returning([])
        await _repo(session).list_by_agent("a1", "r")
        stmt = session.execute.await_args.args[0]
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "agent_id" in sql
        assert "ORDER BY" in sql and "path" in sql


class TestUpsert:

    @pytest.mark.asyncio
    async def test_upsert_emits_on_duplicate_key_update(self):
        session = AsyncMock()
        entity = WikiFolderSummary(
            id="f1", agent_id="a1", path="여신", summary="s",
            article_count=1, updated_at=NOW,
        )
        await _repo(session).upsert(entity, "r")
        stmt = session.execute.await_args.args[0]
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "INSERT INTO wiki_folder_summary" in sql
        assert "ON DUPLICATE KEY UPDATE" in sql
        # 갱신 대상은 요약·건수·시각 — id는 갱신하지 않는다 (uq는 agent_id+path)
        assert "summary" in sql.split("ON DUPLICATE KEY UPDATE")[1]


class TestDelete:

    @pytest.mark.asyncio
    async def test_delete_filters_agent_and_path(self):
        session = AsyncMock()
        await _repo(session).delete("a1", "여신/한도", "r")
        stmt = session.execute.await_args.args[0]
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "DELETE FROM wiki_folder_summary" in sql
        assert "agent_id" in sql and "여신/한도" in sql
