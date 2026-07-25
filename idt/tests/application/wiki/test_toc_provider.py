"""Application 테스트: WikiTocProvider (wiki-agentic-navigation FR-03).

compile 시점 목차 블록 생성 — per-call 세션(RunScopedWikiSearch 패턴),
실패는 빈 문자열 폴백(best-effort, 대화 차단 금지).
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.wiki.schemas import WikiTreeItem
from src.application.wiki.toc_provider import WikiTocProvider

NOW = datetime(2026, 7, 23, tzinfo=timezone.utc)


def _item(id="w1") -> WikiTreeItem:
    return WikiTreeItem(
        id=id, title=f"문서-{id}", status="approved", source_type="human",
        path="여신", updated_at=NOW,
    )


class _SessionCtx:
    def __init__(self, counter):
        self._counter = counter

    async def __aenter__(self):
        self._counter["opened"] += 1
        return MagicMock()

    async def __aexit__(self, *a):
        self._counter["closed"] += 1
        return False


def _make(items=None, raise_exc=False):
    counter = {"opened": 0, "closed": 0}

    def session_factory():
        return _SessionCtx(counter)

    repo = MagicMock()
    if raise_exc:
        repo.list_searchable_tree_items = AsyncMock(side_effect=RuntimeError("db down"))
    else:
        repo.list_searchable_tree_items = AsyncMock(return_value=items or [])

    logger = MagicMock()
    provider = WikiTocProvider(
        session_factory=session_factory,
        repo_builder=lambda session: repo,
        max_items=50,
        max_bytes=4000,
        logger=logger,
    )
    return provider, repo, counter, logger


class TestRenderBlock:

    @pytest.mark.asyncio
    async def test_renders_block_with_items(self):
        provider, repo, counter, _ = _make(items=[_item("w1"), _item("w2")])
        block = await provider.render_block("agent_1", "r")
        assert "(id: w1)" in block and "(id: w2)" in block
        assert "[에이전트 지식 위키 목차]" in block
        repo.list_searchable_tree_items.assert_awaited_once()
        assert repo.list_searchable_tree_items.await_args.args[0] == "agent_1"
        assert counter["opened"] == 1 and counter["closed"] == 1

    @pytest.mark.asyncio
    async def test_empty_items_returns_empty_string(self):
        provider, _, _, _ = _make(items=[])
        assert await provider.render_block("agent_1", "r") == ""

    @pytest.mark.asyncio
    async def test_repo_failure_returns_empty_and_warns(self):
        """목차 실패가 대화를 차단하지 않는다 — best-effort."""
        provider, _, counter, logger = _make(raise_exc=True)
        block = await provider.render_block("agent_1", "r")
        assert block == ""
        logger.warning.assert_called_once()
