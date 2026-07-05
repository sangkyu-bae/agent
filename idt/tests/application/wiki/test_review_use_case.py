"""Application 테스트: WikiReviewUseCase (LLM-WIKI-001, Phase 2/C 거버넌스).

상태 전이(승인/반려/폐기/복구)와 편집을 WikiPolicy로 검증하며 수행한다.
허용되지 않은 전이/미존재 항목은 ValueError로 차단한다.
"""
import pytest

from src.application.wiki.review_use_case import WikiReviewUseCase
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus


class _NullLogger(LoggerInterface):
    def debug(self, m, **k): pass
    def info(self, m, **k): pass
    def warning(self, m, **k): pass
    def error(self, m, exception=None, **k): pass
    def critical(self, m, exception=None, **k): pass


class _FakeRepo:
    def __init__(self, articles=None) -> None:
        self.store = {a.id: a for a in (articles or [])}

    async def find_by_id(self, id, request_id):
        return self.store.get(id)

    async def update(self, article, request_id):
        self.store[article.id] = article
        return article


def _article(id="w1", status=WikiStatus.DRAFT) -> WikiArticle:
    return WikiArticle(
        id=id, agent_id="agent_1", title="t", content="c",
        source_type=WikiSourceType.DISTILLED, source_refs=["doc:1"], status=status,
    )


def _uc(*articles):
    repo = _FakeRepo(list(articles))
    return WikiReviewUseCase(repository=repo, logger=_NullLogger()), repo


class TestApprove:

    @pytest.mark.asyncio
    async def test_draft_to_approved(self):
        uc, repo = _uc(_article(status=WikiStatus.DRAFT))
        result = await uc.approve("w1", reviewer_id="admin", request_id="r")
        assert result.status == WikiStatus.APPROVED
        assert result.reviewer_id == "admin"
        assert repo.store["w1"].status == WikiStatus.APPROVED

    @pytest.mark.asyncio
    async def test_approve_already_approved_rejected(self):
        uc, _ = _uc(_article(status=WikiStatus.APPROVED))
        with pytest.raises(ValueError):
            await uc.approve("w1", reviewer_id="admin", request_id="r")

    @pytest.mark.asyncio
    async def test_approve_missing_raises(self):
        uc, _ = _uc()
        with pytest.raises(ValueError):
            await uc.approve("missing", reviewer_id="admin", request_id="r")


class TestReject:

    @pytest.mark.asyncio
    async def test_draft_to_deprecated(self):
        uc, repo = _uc(_article(status=WikiStatus.DRAFT))
        result = await uc.reject("w1", request_id="r")
        assert result.status == WikiStatus.DEPRECATED
        assert repo.store["w1"].status == WikiStatus.DEPRECATED


class TestDeprecate:

    @pytest.mark.asyncio
    async def test_approved_to_deprecated(self):
        uc, _ = _uc(_article(status=WikiStatus.APPROVED))
        result = await uc.deprecate("w1", request_id="r")
        assert result.status == WikiStatus.DEPRECATED

    @pytest.mark.asyncio
    async def test_deprecate_already_deprecated_rejected(self):
        uc, _ = _uc(_article(status=WikiStatus.DEPRECATED))
        with pytest.raises(ValueError):
            await uc.deprecate("w1", request_id="r")


class TestRestore:

    @pytest.mark.asyncio
    async def test_deprecated_to_approved(self):
        uc, _ = _uc(_article(status=WikiStatus.DEPRECATED))
        result = await uc.restore("w1", reviewer_id="admin", request_id="r")
        assert result.status == WikiStatus.APPROVED
        assert result.reviewer_id == "admin"

    @pytest.mark.asyncio
    async def test_restore_draft_rejected(self):
        uc, _ = _uc(_article(status=WikiStatus.DRAFT))
        with pytest.raises(ValueError):
            await uc.restore("w1", reviewer_id="admin", request_id="r")


class TestEdit:

    @pytest.mark.asyncio
    async def test_edit_updates_and_bumps_version(self):
        uc, repo = _uc(_article())
        result = await uc.edit(
            "w1", title="새 제목", content="새 본문", editor_id="admin", request_id="r"
        )
        assert result.title == "새 제목"
        assert result.content == "새 본문"
        assert result.version == 2
        assert result.editor_id == "admin"
        assert repo.store["w1"].version == 2

    @pytest.mark.asyncio
    async def test_edit_invalid_content_rejected(self):
        uc, _ = _uc(_article())
        with pytest.raises(ValueError):
            await uc.edit("w1", title="t", content="  ", editor_id="admin", request_id="r")

    @pytest.mark.asyncio
    async def test_edit_missing_raises(self):
        uc, _ = _uc()
        with pytest.raises(ValueError):
            await uc.edit("x", title="t", content="c", editor_id="a", request_id="r")
