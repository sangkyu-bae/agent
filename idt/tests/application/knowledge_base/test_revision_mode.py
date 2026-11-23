"""KB revision_mode 설정 — document-revision Design §4.2 #10 (Plan FR-15)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.knowledge_base.use_case import KnowledgeBaseUseCase
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.document_revision.errors import RevisionModeNotAvailableError
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.knowledge_base.policy import KnowledgeBasePolicy


def _uc(repo) -> KnowledgeBaseUseCase:
    return KnowledgeBaseUseCase(
        kb_repo=repo, policy=KnowledgeBasePolicy(), assigner=AsyncMock(),
        dept_repo=AsyncMock(), logger=MagicMock(),
    )


def _user(uid=7) -> User:
    return User(email="a@b.c", password_hash="h", role=UserRole.USER,
                status=UserStatus.APPROVED, id=uid)


@pytest.fixture
def repo() -> AsyncMock:
    r = AsyncMock()
    r.find_by_id.return_value = KnowledgeBase(
        id="kb-1", name="k", owner_id=7, scope=CollectionScope.PERSONAL,
        collection_name="c",
    )
    return r


async def test_suggest_is_saved(repo) -> None:
    await _uc(repo).update_revision_mode("kb-1", _user(), "suggest", "r")
    repo.update_revision_mode.assert_awaited_once_with("kb-1", "suggest", "r")


async def test_auto_is_rejected(repo) -> None:
    with pytest.raises(RevisionModeNotAvailableError):
        await _uc(repo).update_revision_mode("kb-1", _user(), "auto", "r")
    repo.update_revision_mode.assert_not_awaited()


async def test_unknown_mode_is_value_error(repo) -> None:
    with pytest.raises(ValueError):
        await _uc(repo).update_revision_mode("kb-1", _user(), "magic", "r")


async def test_non_owner_rejected(repo) -> None:
    with pytest.raises(PermissionError):
        await _uc(repo).update_revision_mode("kb-1", _user(99), "suggest", "r")
