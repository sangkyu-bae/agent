"""UpdateUserMailboxUseCase — 관리자 메일함 설정·해제.

Design Ref: mcp-identity-header §4.2 (PATCH /admin/users/{id}/mailbox).
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.auth.update_user_mailbox_use_case import (
    UpdateUserMailboxUseCase,
    UserNotFoundError,
)
from src.domain.auth.entities import User, UserStatus


def _user(mailbox=None) -> User:
    return User(id=7, email="kim@login.local", password_hash="h",
                status=UserStatus.APPROVED, mailbox_upn=mailbox)


def _uc(found: User | None):
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=found)
    repo.update_mailbox = AsyncMock()
    return UpdateUserMailboxUseCase(user_repo=repo, logger=MagicMock()), repo


class TestUpdateUserMailbox:
    @pytest.mark.asyncio
    async def test_정규화해_저장하고_갱신된_사용자를_돌려준다(self):
        uc, repo = _uc(_user())
        result = await uc.execute(7, " Kim@Corp.COM ", "r")
        repo.update_mailbox.assert_awaited_once_with(7, "kim@corp.com")
        assert result.mailbox_upn == "kim@corp.com"
        assert result.email == "kim@login.local"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value", [None, "", "  "])
    async def test_빈_값은_해제(self, value):
        uc, repo = _uc(_user(mailbox="old@corp.com"))
        result = await uc.execute(7, value, "r")
        repo.update_mailbox.assert_awaited_once_with(7, None)
        assert result.mailbox_upn is None

    @pytest.mark.asyncio
    async def test_형식_오류는_저장하지_않고_ValueError(self):
        uc, repo = _uc(_user())
        with pytest.raises(ValueError):
            await uc.execute(7, "not-an-email", "r")
        repo.update_mailbox.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_사용자가_없으면_UserNotFoundError(self):
        uc, repo = _uc(None)
        with pytest.raises(UserNotFoundError):
            await uc.execute(99, "kim@corp.com", "r")
        repo.update_mailbox.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_로그에_메일함_주소를_남기지_않는다(self):
        """메일함 주소는 개인정보 — 설정/해제 사실만 기록한다."""
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=_user())
        repo.update_mailbox = AsyncMock()
        logger = MagicMock()
        await UpdateUserMailboxUseCase(user_repo=repo, logger=logger).execute(
            7, "kim@corp.com", "r"
        )
        assert "kim@corp.com" not in str(logger.info.call_args_list)
