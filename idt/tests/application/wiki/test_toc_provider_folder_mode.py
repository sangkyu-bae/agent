"""Application 테스트: WikiTocProvider 폴더 모드 분기 (wiki-folder-summaries D5).

임계 초과+요약 존재 시에만 폴더 지도, 그 외 기존 flat 목차(무회귀 폴백).
"""
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.application.agent_run.prompt_rendering import WIKI_FOLDER_HEADER_TAG
from src.application.wiki.toc_provider import WikiTocProvider
from src.application.wiki.schemas import WikiTreeItem
from src.domain.wiki.entity import WikiFolderSummary

NOW = datetime(2026, 7, 25)


def _item(id, path="여신/한도"):
    return WikiTreeItem(
        id=id, title=f"제목{id}", status="approved", source_type="human",
        path=path, updated_at=NOW,
    )


def _folder(path="여신"):
    return WikiFolderSummary(
        id=f"f-{path}", agent_id="a1", path=path, summary="요약",
        article_count=1, updated_at=NOW,
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


def _provider(items, folders=None, *, folder_enabled=True, threshold=2):
    @asynccontextmanager
    async def session_factory():
        yield MagicMock()

    return WikiTocProvider(
        session_factory=session_factory,
        repo_builder=lambda s: FakeArticleRepo(items),
        max_items=50,
        max_bytes=4000,
        logger=MagicMock(),
        folder_repo_builder=(lambda s: FakeFolderRepo(folders or [])),
        folder_enabled=folder_enabled,
        folder_threshold=threshold,
    )


class TestFolderModeBranch:

    @pytest.mark.asyncio
    async def test_over_threshold_with_summaries_renders_folder_map(self):
        items = [_item(f"w{i}") for i in range(3)]  # 3 > threshold 2
        block = await _provider(items, [_folder("여신"), _folder("여신/한도")]).render_block(
            "a1", "r"
        )
        assert block.startswith(WIKI_FOLDER_HEADER_TAG)
        # 최상위(1세그먼트) 폴더만 지도에 노출
        assert "- 여신 — " in block
        assert "여신/한도 — " not in block

    @pytest.mark.asyncio
    async def test_under_threshold_keeps_flat_toc(self):
        items = [_item("w1")]
        block = await _provider(items, [_folder()]).render_block("a1", "r")
        assert "[에이전트 지식 위키 목차]" in block
        assert WIKI_FOLDER_HEADER_TAG not in block

    @pytest.mark.asyncio
    async def test_no_summaries_falls_back_to_flat(self):
        """증류 전/전부 실패 — flat 폴백으로 기능 저하 없음."""
        items = [_item(f"w{i}") for i in range(3)]
        block = await _provider(items, []).render_block("a1", "r")
        assert "[에이전트 지식 위키 목차]" in block

    @pytest.mark.asyncio
    async def test_disabled_keeps_flat_even_over_threshold(self):
        items = [_item(f"w{i}") for i in range(3)]
        block = await _provider(
            items, [_folder()], folder_enabled=False
        ).render_block("a1", "r")
        assert "[에이전트 지식 위키 목차]" in block

    @pytest.mark.asyncio
    async def test_uncategorized_count_passed(self):
        items = [_item("w1", path=None), _item("w2"), _item("w3")]
        block = await _provider(items, [_folder()]).render_block("a1", "r")
        assert "(미분류)" in block and "1건" in block

    @pytest.mark.asyncio
    async def test_legacy_ctor_without_folder_args_still_flat(self):
        """기존 배선(폴더 인자 미주입) 무회귀."""

        @asynccontextmanager
        async def session_factory():
            yield MagicMock()

        provider = WikiTocProvider(
            session_factory=session_factory,
            repo_builder=lambda s: FakeArticleRepo([_item("w1")]),
            max_items=50, max_bytes=4000, logger=MagicMock(),
        )
        block = await provider.render_block("a1", "r")
        assert "[에이전트 지식 위키 목차]" in block
