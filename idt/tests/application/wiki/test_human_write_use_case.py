"""Application 테스트: HumanWikiWriteUseCase (wiki-user-facing).

소유자 직접 작성(즉시 approved)·편집·폐기 + 인가(can_manage) 검증.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.application.wiki.human_write_use_case import HumanWikiWriteUseCase
from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus
from src.domain.wiki.policies import WikiPolicy

OWNER_ID = "7"
OTHER_ID = "8"
AGENT_ID = "agent_1"


class _FakeWikiRepo:
    def __init__(self, articles=None) -> None:
        self.store = {a.id: a for a in (articles or [])}
        self.saved = []
        self.updated = []

    async def save(self, article, request_id):
        self.saved.append(article)
        self.store[article.id] = article
        return article

    async def update(self, article, request_id):
        self.updated.append(article)
        self.store[article.id] = article
        return article

    async def find_by_id(self, id, request_id):
        return self.store.get(id)


class _FakeAgentRepo:
    def __init__(self, agents=None) -> None:
        self._agents = agents or {AGENT_ID: SimpleNamespace(user_id=OWNER_ID)}

    async def find_by_id(self, agent_id, request_id):
        return self._agents.get(agent_id)


def _human_article(id="w1", agent_id=AGENT_ID):
    return WikiArticle(
        id=id, agent_id=agent_id, title="t", content="c",
        source_type=WikiSourceType.HUMAN,
        source_refs=[WikiPolicy.human_source_ref(OWNER_ID)],
        status=WikiStatus.APPROVED, path="여신/한도",
    )


def _distilled_article(id="w2", agent_id=AGENT_ID):
    return WikiArticle(
        id=id, agent_id=agent_id, title="t", content="c",
        source_type=WikiSourceType.DISTILLED, source_refs=["doc:1"],
        status=WikiStatus.APPROVED,
    )


def _uc(wiki_repo=None, agent_repo=None):
    return HumanWikiWriteUseCase(
        wiki_repo=wiki_repo or _FakeWikiRepo(),
        agent_repo=agent_repo or _FakeAgentRepo(),
        logger=MagicMock(),
    )


class TestCreate:

    @pytest.mark.asyncio
    async def test_owner_creates_immediately_approved(self):
        repo = _FakeWikiRepo()
        uc = _uc(wiki_repo=repo)
        article = await uc.create(
            agent_id=AGENT_ID, title="제목", content="본문", path="여신/한도",
            actor_id=OWNER_ID, actor_is_admin=False, request_id="r",
        )
        assert article.status == WikiStatus.APPROVED
        assert article.source_type == WikiSourceType.HUMAN
        assert article.source_refs == [f"human:{OWNER_ID}"]
        assert article.editor_id == OWNER_ID
        assert article.reviewer_id == OWNER_ID
        assert article.path == "여신/한도"
        assert len(repo.saved) == 1

    @pytest.mark.asyncio
    async def test_admin_can_create_for_any_agent(self):
        article = await _uc().create(
            agent_id=AGENT_ID, title="제목", content="본문", path=None,
            actor_id="99", actor_is_admin=True, request_id="r",
        )
        assert article.status == WikiStatus.APPROVED
        assert article.source_refs == ["human:99"]

    @pytest.mark.asyncio
    async def test_non_owner_rejected(self):
        with pytest.raises(PermissionError):
            await _uc().create(
                agent_id=AGENT_ID, title="제목", content="본문", path=None,
                actor_id=OTHER_ID, actor_is_admin=False, request_id="r",
            )

    @pytest.mark.asyncio
    async def test_missing_agent_rejected(self):
        uc = _uc(agent_repo=_FakeAgentRepo(agents={}))
        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.create(
                agent_id="nope", title="제목", content="본문", path=None,
                actor_id=OWNER_ID, actor_is_admin=False, request_id="r",
            )

    @pytest.mark.asyncio
    async def test_invalid_path_rejected(self):
        with pytest.raises(ValueError):
            await _uc().create(
                agent_id=AGENT_ID, title="제목", content="본문", path="a/b/c/d",
                actor_id=OWNER_ID, actor_is_admin=False, request_id="r",
            )

    @pytest.mark.asyncio
    async def test_creation_invariant_applied(self):
        with pytest.raises(ValueError):
            await _uc().create(
                agent_id=AGENT_ID, title="  ", content="본문", path=None,
                actor_id=OWNER_ID, actor_is_admin=False, request_id="r",
            )


class TestEdit:

    @pytest.mark.asyncio
    async def test_owner_edits_own_human(self):
        repo = _FakeWikiRepo([_human_article("w1")])
        uc = _uc(wiki_repo=repo)
        article = await uc.edit(
            article_id="w1", title="새제목", content="새본문", path="여신",
            actor_id=OWNER_ID, actor_is_admin=False, request_id="r",
        )
        assert article.title == "새제목"
        assert article.version == 2
        assert article.path == "여신"
        assert article.editor_id == OWNER_ID
        assert len(repo.updated) == 1

    @pytest.mark.asyncio
    async def test_owner_cannot_edit_distilled(self):
        repo = _FakeWikiRepo([_distilled_article("w2")])
        uc = _uc(wiki_repo=repo)
        with pytest.raises(PermissionError):
            await uc.edit(
                article_id="w2", title="t", content="c", path=None,
                actor_id=OWNER_ID, actor_is_admin=False, request_id="r",
            )

    @pytest.mark.asyncio
    async def test_admin_can_edit_distilled(self):
        repo = _FakeWikiRepo([_distilled_article("w2")])
        uc = _uc(wiki_repo=repo)
        article = await uc.edit(
            article_id="w2", title="정정", content="c2", path=None,
            actor_id="99", actor_is_admin=True, request_id="r",
        )
        assert article.title == "정정"

    @pytest.mark.asyncio
    async def test_non_owner_cannot_edit_human(self):
        repo = _FakeWikiRepo([_human_article("w1")])
        uc = _uc(wiki_repo=repo)
        with pytest.raises(PermissionError):
            await uc.edit(
                article_id="w1", title="t", content="c", path=None,
                actor_id=OTHER_ID, actor_is_admin=False, request_id="r",
            )

    @pytest.mark.asyncio
    async def test_missing_article_rejected(self):
        with pytest.raises(ValueError, match="찾을 수 없"):
            await _uc().edit(
                article_id="nope", title="t", content="c", path=None,
                actor_id=OWNER_ID, actor_is_admin=False, request_id="r",
            )


class TestDeprecate:

    @pytest.mark.asyncio
    async def test_owner_deprecates_own_human(self):
        repo = _FakeWikiRepo([_human_article("w1")])
        uc = _uc(wiki_repo=repo)
        article = await uc.deprecate(
            article_id="w1", actor_id=OWNER_ID, actor_is_admin=False, request_id="r",
        )
        assert article.status == WikiStatus.DEPRECATED

    @pytest.mark.asyncio
    async def test_owner_cannot_deprecate_distilled(self):
        repo = _FakeWikiRepo([_distilled_article("w2")])
        uc = _uc(wiki_repo=repo)
        with pytest.raises(PermissionError):
            await uc.deprecate(
                article_id="w2", actor_id=OWNER_ID, actor_is_admin=False,
                request_id="r",
            )

    @pytest.mark.asyncio
    async def test_transition_validated(self):
        """이미 deprecated인 항목의 재폐기는 전이 규칙 위반(ValueError)."""
        article = _human_article("w1")
        article.status = WikiStatus.DEPRECATED
        repo = _FakeWikiRepo([article])
        uc = _uc(wiki_repo=repo)
        with pytest.raises(ValueError):
            await uc.deprecate(
                article_id="w1", actor_id=OWNER_ID, actor_is_admin=False,
                request_id="r",
            )
