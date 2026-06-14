"""Grant/Revoke Permission UseCase 단위 테스트."""
from unittest.mock import AsyncMock

import pytest

from src.application.permission.grant_revoke import (
    GrantPermissionUseCase,
    RevokePermissionUseCase,
)


def _logger():
    log = AsyncMock()
    log.info = lambda *a, **k: None
    log.error = lambda *a, **k: None
    return log


class TestGrantPermission:
    @pytest.mark.asyncio
    async def test_valid_code_delegates_to_repo(self):
        repo = AsyncMock()
        uc = GrantPermissionUseCase(permission_repo=repo, logger=_logger())
        await uc.execute(user_id=1, code="USE_RAG_SEARCH", granted_by=2, request_id="r")
        repo.grant_to_user.assert_awaited_with(
            user_id=1, code="USE_RAG_SEARCH", granted_by=2, request_id="r",
        )

    @pytest.mark.asyncio
    async def test_unknown_code_raises(self):
        repo = AsyncMock()
        uc = GrantPermissionUseCase(permission_repo=repo, logger=_logger())
        with pytest.raises(ValueError, match="Unknown permission code"):
            await uc.execute(user_id=1, code="HACK_THE_PLANET", granted_by=2, request_id="r")
        repo.grant_to_user.assert_not_awaited()


class TestRevokePermission:
    @pytest.mark.asyncio
    async def test_valid_code_delegates_to_repo(self):
        repo = AsyncMock()
        uc = RevokePermissionUseCase(permission_repo=repo, logger=_logger())
        await uc.execute(user_id=1, code="MANAGE_USERS", request_id="r")
        repo.revoke_from_user.assert_awaited_with(
            user_id=1, code="MANAGE_USERS", request_id="r",
        )

    @pytest.mark.asyncio
    async def test_unknown_code_raises(self):
        repo = AsyncMock()
        uc = RevokePermissionUseCase(permission_repo=repo, logger=_logger())
        with pytest.raises(ValueError, match="Unknown permission code"):
            await uc.execute(user_id=1, code="UNKNOWN", request_id="r")
        repo.revoke_from_user.assert_not_awaited()
