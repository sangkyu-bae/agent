"""Application 테스트: WikiQueryUseCase (LLM-WIKI-001, 조회 전용)."""
import pytest

from src.application.wiki.query_use_case import WikiQueryUseCase
from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus


class _FakeRepo:
    def __init__(self, articles=None) -> None:
        self.store = {a.id: a for a in (articles or [])}
        self.last_status = "UNSET"

    async def find_by_id(self, id, request_id):
        return self.store.get(id)

    async def find_by_agent(self, agent_id, request_id, status=None):
        self.last_status = status
        items = [a for a in self.store.values() if a.agent_id == agent_id]
        if status is not None:
            items = [a for a in items if a.status == status]
        return items


def _a(id="w1", status=WikiStatus.DRAFT):
    return WikiArticle(
        id=id, agent_id="agent_1", title="t", content="c",
        source_type=WikiSourceType.DISTILLED, source_refs=["doc:1"], status=status,
    )


class TestQuery:

    @pytest.mark.asyncio
    async def test_get_by_id(self):
        uc = WikiQueryUseCase(_FakeRepo([_a("w1")]))
        result = await uc.get_by_id("w1", "r")
        assert result is not None and result.id == "w1"

    @pytest.mark.asyncio
    async def test_get_by_id_none(self):
        uc = WikiQueryUseCase(_FakeRepo())
        assert await uc.get_by_id("x", "r") is None

    @pytest.mark.asyncio
    async def test_list_by_agent_passes_status_filter(self):
        repo = _FakeRepo([_a("w1", WikiStatus.DRAFT), _a("w2", WikiStatus.APPROVED)])
        uc = WikiQueryUseCase(repo)
        result = await uc.list_by_agent("agent_1", "r", status=WikiStatus.APPROVED)
        assert [a.id for a in result] == ["w2"]
        assert repo.last_status == WikiStatus.APPROVED

    @pytest.mark.asyncio
    async def test_list_by_agent_no_filter(self):
        repo = _FakeRepo([_a("w1"), _a("w2")])
        uc = WikiQueryUseCase(repo)
        result = await uc.list_by_agent("agent_1", "r")
        assert len(result) == 2
        assert repo.last_status is None
