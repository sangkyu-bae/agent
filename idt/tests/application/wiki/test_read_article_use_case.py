"""Application 테스트: WikiArticleReadUseCase (wiki-agentic-navigation FR-02).

agent 소유 + 승인 + 미만료 위키 단건 열람. 실패 사유는 구분하지 않고
전부 None으로 수렴한다(id 존재 여부 오라클 차단).
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.wiki.read_article_use_case import WikiArticleReadUseCase
from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus

NOW = datetime(2026, 7, 23, tzinfo=timezone.utc)


def _article(
    id="w1",
    agent_id="agent_1",
    status=WikiStatus.APPROVED,
    valid_until=None,
) -> WikiArticle:
    return WikiArticle(
        id=id, agent_id=agent_id, title=f"t-{id}", content=f"c-{id}",
        source_type=WikiSourceType.DISTILLED, source_refs=["doc:1"],
        status=status, confidence=0.8, valid_until=valid_until,
    )


def _use_case(found: WikiArticle | None) -> tuple[WikiArticleReadUseCase, MagicMock]:
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=found)
    return WikiArticleReadUseCase(wiki_repo=repo), repo


class TestGuards:

    @pytest.mark.asyncio
    async def test_not_found_returns_none(self):
        use_case, repo = _use_case(found=None)
        result = await use_case.execute("missing", "agent_1", NOW, "r")
        assert result is None
        repo.find_by_id.assert_awaited_once_with("missing", "r")

    @pytest.mark.asyncio
    async def test_other_agent_article_returns_none(self):
        use_case, _ = _use_case(found=_article(agent_id="agent_other"))
        assert await use_case.execute("w1", "agent_1", NOW, "r") is None

    @pytest.mark.asyncio
    async def test_draft_returns_none(self):
        use_case, _ = _use_case(found=_article(status=WikiStatus.DRAFT))
        assert await use_case.execute("w1", "agent_1", NOW, "r") is None

    @pytest.mark.asyncio
    async def test_deprecated_returns_none(self):
        use_case, _ = _use_case(found=_article(status=WikiStatus.DEPRECATED))
        assert await use_case.execute("w1", "agent_1", NOW, "r") is None

    @pytest.mark.asyncio
    async def test_expired_returns_none(self):
        expired = _article(valid_until=NOW - timedelta(seconds=1))
        use_case, _ = _use_case(found=expired)
        assert await use_case.execute("w1", "agent_1", NOW, "r") is None


class TestSuccess:

    @pytest.mark.asyncio
    async def test_owned_approved_unexpired_returns_article(self):
        article = _article(valid_until=NOW + timedelta(days=1))
        use_case, _ = _use_case(found=article)
        result = await use_case.execute("w1", "agent_1", NOW, "r")
        assert result is article

    @pytest.mark.asyncio
    async def test_no_expiry_returns_article(self):
        article = _article(valid_until=None)
        use_case, _ = _use_case(found=article)
        assert await use_case.execute("w1", "agent_1", NOW, "r") is article
