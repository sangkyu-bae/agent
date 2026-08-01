"""Infrastructure 테스트: WikiListTool (wiki-folder-summaries D4).

폴더 진입 도구 — RunContext 격리, 오라클 차단(단일 실패 문구),
루트/하위 폴더/미분류 렌더를 페이크 저장소로 검증.
"""
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.application.agent_run.context import RunContext, set_current_run_context
from src.application.wiki.schemas import WikiTreeItem
from src.domain.wiki.entity import WikiFolderSummary
from src.infrastructure.wiki.wiki_list_tool import FAIL_TEXT, WikiListTool

NOW = datetime(2026, 7, 25)


def _item(id="w1", title="제목", path="여신/한도"):
    return WikiTreeItem(
        id=id, title=title, status="approved", source_type="human",
        path=path, updated_at=NOW,
    )


def _folder(path="여신", summary="여신 관련 지식", count=3):
    return WikiFolderSummary(
        id=f"f-{path}", agent_id="a1", path=path, summary=summary,
        article_count=count, updated_at=NOW,
    )


class FakeArticleRepo:
    def __init__(self, items):
        self._items = items

    async def list_searchable_tree_items(self, agent_id, now, request_id):
        return self._items


class FakeFolderRepo:
    def __init__(self, folders):
        self._folders = folders

    async def list_by_agent(self, agent_id, request_id):
        return self._folders


def _tool(items=None, folders=None):
    @asynccontextmanager
    async def session_factory():
        yield MagicMock()

    return WikiListTool(
        session_factory=session_factory,
        repo_builder=lambda s: FakeArticleRepo(items or []),
        folder_repo_builder=lambda s: FakeFolderRepo(folders or []),
        request_id="r",
        logger=MagicMock(),
    )


def _set_ctx(agent_id="a1"):
    set_current_run_context(
        RunContext(
            run_id="run1", agent_id=agent_id, user_id="u1", callback=MagicMock()
        )
    )


class TestWikiListTool:

    def teardown_method(self):
        set_current_run_context(None)

    @pytest.mark.asyncio
    async def test_no_run_context_returns_fail(self):
        set_current_run_context(None)
        out = await _tool()._arun(path="여신")
        assert out == FAIL_TEXT

    @pytest.mark.asyncio
    async def test_unknown_path_returns_single_fail_text(self):
        """미존재 path — 오라클 차단: 존재 여부를 구분할 수 없는 단일 문구."""
        _set_ctx()
        out = await _tool(items=[_item()], folders=[_folder()])._arun(path="없는폴더")
        assert out == FAIL_TEXT

    @pytest.mark.asyncio
    async def test_folder_lists_children_and_direct_docs(self):
        _set_ctx()
        tool = _tool(
            items=[_item("w1", "한도문서", "여신/한도"), _item("w2", "직속문서", "여신")],
            folders=[_folder("여신"), _folder("여신/한도", "한도 지식", 1)],
        )
        out = await tool._arun(path="여신")
        assert "[위키 폴더: 여신]" in out
        assert "여신/한도 — 한도 지식 (1건)" in out
        assert "(id: w2) 직속문서" in out
        # 하위 폴더 소속 문서는 직속 목록에 나오지 않는다
        assert "w1" not in out
        assert "wiki_read" in out  # 하단 후속 행동 지시

    @pytest.mark.asyncio
    async def test_root_lists_top_folders_and_uncategorized(self):
        _set_ctx()
        tool = _tool(
            items=[_item("w1", "미분류문서", None), _item("w2", "d", "여신/한도")],
            folders=[_folder("여신"), _folder("여신/한도")],
        )
        out = await tool._arun(path="")
        assert "[위키 폴더: 루트]" in out
        assert "여신 — " in out
        # 루트에는 최상위 폴더만 — 2뎁스는 진입 후 노출
        assert "여신/한도 — " not in out
        assert "(id: w1) 미분류문서" in out

    @pytest.mark.asyncio
    async def test_docs_rendered_realtime_even_without_summary(self):
        """요약 row가 없어도(증류 전) 실시간 문서 목록은 나온다 — 목록이 진실."""
        _set_ctx()
        out = await _tool(items=[_item("w1", "문서", "여신")], folders=[])._arun(
            path="여신"
        )
        assert "(id: w1) 문서" in out
