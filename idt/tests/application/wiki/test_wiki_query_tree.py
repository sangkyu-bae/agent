"""Application 테스트: WikiQueryUseCase.list_tree (wiki-user-facing).

path 문자열 단위 그룹핑(서버) — 계층 조립은 프론트 담당.
"""
from datetime import datetime

import pytest

from src.application.wiki.query_use_case import WikiQueryUseCase
from src.application.wiki.schemas import WikiTreeItem

NOW = datetime(2026, 7, 18)


class _FakeRepo:
    def __init__(self, items=None) -> None:
        self.items = items or []

    async def list_tree_items(self, agent_id, request_id):
        return self.items


def _item(id, path, title="t"):
    return WikiTreeItem(
        id=id, title=title, status="approved", source_type="human",
        path=path, updated_at=NOW,
    )


class TestListTree:

    @pytest.mark.asyncio
    async def test_groups_by_exact_path(self):
        repo = _FakeRepo([
            _item("w1", "여신/한도"),
            _item("w2", "여신/한도"),
            _item("w3", "여신"),
        ])
        groups = await WikiQueryUseCase(repo).list_tree("agent_1", "r")
        by_path = {g.path: [i.id for i in g.items] for g in groups}
        assert by_path == {"여신/한도": ["w1", "w2"], "여신": ["w3"]}

    @pytest.mark.asyncio
    async def test_null_path_grouped_as_unclassified(self):
        repo = _FakeRepo([_item("w1", None), _item("w2", "여신")])
        groups = await WikiQueryUseCase(repo).list_tree("agent_1", "r")
        assert {g.path for g in groups} == {None, "여신"}

    @pytest.mark.asyncio
    async def test_group_order_preserves_repo_order(self):
        """repo가 path 정렬(미분류 마지막)로 반환 — 그룹 순서는 첫 등장 순."""
        repo = _FakeRepo([
            _item("w1", "가"), _item("w2", "나"), _item("w3", None),
        ])
        groups = await WikiQueryUseCase(repo).list_tree("agent_1", "r")
        assert [g.path for g in groups] == ["가", "나", None]

    @pytest.mark.asyncio
    async def test_empty(self):
        groups = await WikiQueryUseCase(_FakeRepo()).list_tree("agent_1", "r")
        assert groups == []
