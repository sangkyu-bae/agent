"""Application 테스트: WikiArticleRepository 추상 계약 (LLM-WIKI-001).

인터페이스가 ABC로서 강제력을 갖는지(미구현 시 인스턴스화 불가)와
완전 구현(Fake)이 계약을 만족하는지 검증한다.
"""
from datetime import datetime

import pytest

from src.application.repositories.wiki_repository import WikiArticleRepository
from src.application.wiki.schemas import WikiTreeItem
from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus


def _article(**kw) -> WikiArticle:
    base = dict(
        id="w1", agent_id="agent_1", title="t", content="c",
        source_type=WikiSourceType.DISTILLED, source_refs=["doc:1"],
    )
    base.update(kw)
    return WikiArticle(**base)


class _FakeWikiRepo(WikiArticleRepository):
    """계약 충족용 인메모리 구현."""

    def __init__(self) -> None:
        self._store: dict[str, WikiArticle] = {}

    async def save(self, article: WikiArticle, request_id: str) -> WikiArticle:
        self._store[article.id] = article
        return article

    async def find_by_id(self, id: str, request_id: str) -> WikiArticle | None:
        return self._store.get(id)

    async def find_by_agent(
        self, agent_id: str, request_id: str, status: WikiStatus | None = None
    ) -> list[WikiArticle]:
        items = [a for a in self._store.values() if a.agent_id == agent_id]
        if status is not None:
            items = [a for a in items if a.status == status]
        return items

    async def update(self, article: WikiArticle, request_id: str) -> WikiArticle:
        self._store[article.id] = article
        return article

    async def delete(self, id: str, request_id: str) -> bool:
        return self._store.pop(id, None) is not None

    async def search_similar(
        self, agent_id: str, query: str, top_k: int, now: datetime, request_id: str
    ) -> list[WikiArticle]:
        return [
            a for a in self._store.values()
            if a.agent_id == agent_id and a.is_searchable(now)
        ][:top_k]

    async def list_tree_items(
        self, agent_id: str, request_id: str
    ) -> list[WikiTreeItem]:
        return [
            WikiTreeItem(
                id=a.id, title=a.title, status=a.status.value,
                source_type=a.source_type.value, path=a.path,
                updated_at=a.updated_at,
            )
            for a in self._store.values()
            if a.agent_id == agent_id
        ]


class TestAbstractContract:

    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            WikiArticleRepository()  # type: ignore[abstract]

    def test_incomplete_subclass_cannot_instantiate(self):
        class _Partial(WikiArticleRepository):
            async def save(self, article, request_id):
                return article

        with pytest.raises(TypeError):
            _Partial()  # type: ignore[abstract]

    def test_complete_subclass_instantiates(self):
        assert isinstance(_FakeWikiRepo(), WikiArticleRepository)


class TestFakeBehaviorMatchesContract:

    @pytest.mark.asyncio
    async def test_save_and_find_by_id(self):
        repo = _FakeWikiRepo()
        await repo.save(_article(id="w1"), request_id="r")
        found = await repo.find_by_id("w1", request_id="r")
        assert found is not None and found.id == "w1"

    @pytest.mark.asyncio
    async def test_find_by_agent_status_filter(self):
        repo = _FakeWikiRepo()
        await repo.save(_article(id="w1", status=WikiStatus.DRAFT), "r")
        await repo.save(_article(id="w2", status=WikiStatus.APPROVED), "r")
        approved = await repo.find_by_agent("agent_1", "r", status=WikiStatus.APPROVED)
        assert [a.id for a in approved] == ["w2"]

    @pytest.mark.asyncio
    async def test_search_similar_returns_only_searchable(self):
        repo = _FakeWikiRepo()
        await repo.save(_article(id="w1", status=WikiStatus.DRAFT), "r")
        await repo.save(_article(id="w2", status=WikiStatus.APPROVED), "r")
        now = datetime(2026, 6, 28)
        hits = await repo.search_similar("agent_1", "q", top_k=5, now=now, request_id="r")
        assert [a.id for a in hits] == ["w2"]

    @pytest.mark.asyncio
    async def test_delete(self):
        repo = _FakeWikiRepo()
        await repo.save(_article(id="w1"), "r")
        assert await repo.delete("w1", "r") is True
        assert await repo.find_by_id("w1", "r") is None
