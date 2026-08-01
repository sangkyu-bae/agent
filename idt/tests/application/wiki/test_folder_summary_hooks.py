"""Application 테스트: 승인 이벤트 → 폴더 요약 kickoff 훅 (wiki-folder-summaries D2).

WikiReviewUseCase / HumanWikiWriteUseCase의 optional 의존(기본 None=no-op)을 검증.
"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.wiki.human_write_use_case import HumanWikiWriteUseCase
from src.application.wiki.review_use_case import WikiReviewUseCase
from src.domain.wiki.entity import WikiArticle, WikiSourceType, WikiStatus

NOW = datetime(2026, 7, 25)


def _article(status=WikiStatus.DRAFT, path="여신/한도", source=WikiSourceType.HUMAN):
    return WikiArticle(
        id="w1", agent_id="a1", title="제목", content="본문",
        source_type=source, source_refs=["human:u1"],
        status=status, created_at=NOW, updated_at=NOW, path=path,
    )


def _repo(article):
    repo = AsyncMock()
    repo.find_by_id = AsyncMock(return_value=article)
    repo.update = AsyncMock(side_effect=lambda a, r: a)
    repo.save = AsyncMock(side_effect=lambda a, r: a)
    return repo


def _agent_repo(owner="u1"):
    repo = AsyncMock()
    agent = MagicMock()
    agent.user_id = owner
    repo.find_by_id = AsyncMock(return_value=agent)
    return repo


class TestReviewUseCaseHook:

    @pytest.mark.asyncio
    async def test_approve_kicks_off_with_article_path(self):
        svc = MagicMock()
        uc = WikiReviewUseCase(
            repository=_repo(_article()), logger=MagicMock(),
            folder_summary_service=svc,
        )
        await uc.approve("w1", "admin", "r")
        svc.kickoff_refresh.assert_called_once_with("a1", ["여신/한도"], "r")

    @pytest.mark.asyncio
    async def test_deprecate_kicks_off(self):
        svc = MagicMock()
        uc = WikiReviewUseCase(
            repository=_repo(_article(status=WikiStatus.APPROVED)),
            logger=MagicMock(), folder_summary_service=svc,
        )
        await uc.deprecate("w1", "r")
        svc.kickoff_refresh.assert_called_once_with("a1", ["여신/한도"], "r")

    @pytest.mark.asyncio
    async def test_edit_kicks_off(self):
        svc = MagicMock()
        uc = WikiReviewUseCase(
            repository=_repo(_article(status=WikiStatus.APPROVED)),
            logger=MagicMock(), folder_summary_service=svc,
        )
        await uc.edit("w1", "새제목", "새본문", "u1", "r")
        svc.kickoff_refresh.assert_called_once_with("a1", ["여신/한도"], "r")

    @pytest.mark.asyncio
    async def test_default_none_service_no_error(self):
        """optional 의존 무회귀 — 미주입이면 훅 없이 기존 동작."""
        uc = WikiReviewUseCase(repository=_repo(_article()), logger=MagicMock())
        result = await uc.approve("w1", "admin", "r")
        assert result.status == WikiStatus.APPROVED

    @pytest.mark.asyncio
    async def test_failed_transition_does_not_kickoff(self):
        svc = MagicMock()
        uc = WikiReviewUseCase(
            repository=_repo(_article(status=WikiStatus.APPROVED)),
            logger=MagicMock(), folder_summary_service=svc,
        )
        with pytest.raises(ValueError):
            await uc.approve("w1", "admin", "r")  # approved→approved 불가
        svc.kickoff_refresh.assert_not_called()


class TestHumanWriteHook:

    @pytest.mark.asyncio
    async def test_create_kicks_off(self):
        svc = MagicMock()
        uc = HumanWikiWriteUseCase(
            wiki_repo=_repo(None), agent_repo=_agent_repo(), logger=MagicMock(),
            folder_summary_service=svc,
        )
        await uc.create(
            agent_id="a1", title="제목", content="본문", path="여신",
            actor_id="u1", actor_is_admin=False, request_id="r",
        )
        svc.kickoff_refresh.assert_called_once_with("a1", ["여신"], "r")

    @pytest.mark.asyncio
    async def test_edit_path_change_kicks_off_both_paths(self):
        """path 이동 — 이전/새 폴더 모두 재증류 대상."""
        svc = MagicMock()
        uc = HumanWikiWriteUseCase(
            wiki_repo=_repo(_article(status=WikiStatus.APPROVED, path="여신/한도")),
            agent_repo=_agent_repo(), logger=MagicMock(),
            folder_summary_service=svc,
        )
        await uc.edit(
            article_id="w1", title="제목", content="본문", path="여신/심사",
            actor_id="u1", actor_is_admin=False, request_id="r",
        )
        svc.kickoff_refresh.assert_called_once_with(
            "a1", ["여신/한도", "여신/심사"], "r"
        )

    @pytest.mark.asyncio
    async def test_deprecate_kicks_off(self):
        svc = MagicMock()
        uc = HumanWikiWriteUseCase(
            wiki_repo=_repo(_article(status=WikiStatus.APPROVED)),
            agent_repo=_agent_repo(), logger=MagicMock(),
            folder_summary_service=svc,
        )
        await uc.deprecate(
            article_id="w1", actor_id="u1", actor_is_admin=False, request_id="r"
        )
        svc.kickoff_refresh.assert_called_once_with("a1", ["여신/한도"], "r")
