"""Infrastructure 테스트: list_tree_items (knowledge-deprecate-visibility).

지식 트리용 경량 조회. 폐기(deprecated) 문서는 트리에서 제외하되
draft 노출은 유지한다 — 컴파일된 쿼리 문자열로 필터·정렬 의미를 고정한다
(test_wiki_repository_toc의 D7 패턴 미러).
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.wiki.schemas import WikiTreeItem
from src.infrastructure.wiki.wiki_repository import WikiArticleRepository

NOW = datetime(2026, 8, 2, tzinfo=timezone.utc)


def _repo(session):
    return WikiArticleRepository(
        session=session, logger=MagicMock(),
        embedding=MagicMock(), vector_store=MagicMock(),
        collection_name="wiki_knowledge",
    )


def _row(id="w1", title="제목", path="여신/한도", status="approved"):
    r = MagicMock()
    r.id = id
    r.title = title
    r.status = status
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


def _compiled_sql(session) -> str:
    stmt = session.execute.await_args.args[0]
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


class TestListTreeItems:

    @pytest.mark.asyncio
    async def test_maps_rows_to_tree_items(self):
        session = _session_returning([_row("w2"), _row("w1", status="draft")])
        repo = _repo(session)
        items = await repo.list_tree_items("agent_1", "r")
        assert [i.id for i in items] == ["w2", "w1"]
        assert all(isinstance(i, WikiTreeItem) for i in items)

    @pytest.mark.asyncio
    async def test_query_excludes_deprecated(self):
        """B1: 폐기 문서는 SQL WHERE로 제외 — 후처리 필터 금지."""
        session = _session_returning([])
        repo = _repo(session)
        await repo.list_tree_items("agent_1", "r")

        sql = _compiled_sql(session)
        assert "status != 'deprecated'" in sql

    @pytest.mark.asyncio
    async def test_query_keeps_agent_filter_and_path_order(self):
        """B2: agent 격리 필터와 path·최신순 정렬 유지."""
        session = _session_returning([])
        repo = _repo(session)
        await repo.list_tree_items("agent_1", "r")

        sql = _compiled_sql(session)
        assert "agent_id" in sql
        assert "path IS NULL" in sql
        assert "ORDER BY" in sql and "updated_at DESC" in sql

    @pytest.mark.asyncio
    async def test_query_does_not_filter_draft(self):
        """B3 (FR-03): draft는 트리에 노출 유지 — 과필터 회귀 방지."""
        session = _session_returning([])
        repo = _repo(session)
        await repo.list_tree_items("agent_1", "r")

        sql = _compiled_sql(session)
        assert "'draft'" not in sql
        assert "status = 'approved'" not in sql

    @pytest.mark.asyncio
    async def test_lightweight_no_content_column(self):
        """B4: 본문 미조회(경량) — content 컬럼이 SELECT에 없어야 한다."""
        session = _session_returning([])
        repo = _repo(session)
        await repo.list_tree_items("agent_1", "r")

        sql = _compiled_sql(session)
        assert "content" not in sql.split("FROM")[0]
