"""KnowledgeBaseUploadUseCase의 청킹 위임 검증 (clause-aware-chunking Design §10)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.knowledge_base.upload_use_case import (
    KnowledgeBaseUploadUseCase,
)
from src.application.unified_upload.schemas import UploadChunkingConfig
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.knowledge_base.entities import KnowledgeBase
from src.domain.knowledge_base.policy import KnowledgeBasePolicy


def _user():
    return User(
        id=1, email="a@b.c", password_hash="h",
        role=UserRole.USER, status=UserStatus.APPROVED,
    )


def _kb():
    return KnowledgeBase(
        id="kb1", name="kb", owner_id=1,
        scope=CollectionScope.PERSONAL, collection_name="col",
        use_clause_chunking=True,
    )


@pytest.fixture
def kb_repo():
    r = AsyncMock()
    r.find_by_id.return_value = _kb()
    return r


@pytest.fixture
def unified():
    u = AsyncMock()
    u.execute.return_value = MagicMock()
    return u


@pytest.fixture
def dept_repo():
    r = AsyncMock()
    r.find_departments_by_user.return_value = []
    return r


def _build(kb_repo, unified, dept_repo, resolver):
    return KnowledgeBaseUploadUseCase(
        kb_repo=kb_repo,
        policy=KnowledgeBasePolicy(),
        dept_repo=dept_repo,
        unified_upload=unified,
        logger=MagicMock(),
        chunking_resolver=resolver,
    )


class TestChunkingDelegation:
    @pytest.mark.asyncio
    async def test_resolver_config_passed_to_request(
        self, kb_repo, unified, dept_repo
    ):
        cfg = UploadChunkingConfig(strategy="clause_aware", params={}, display={})
        resolver = AsyncMock()
        resolver.resolve.return_value = cfg
        uc = _build(kb_repo, unified, dept_repo, resolver)

        await uc.execute("kb1", _user(), b"x", "f.pdf", "r")

        req = unified.execute.call_args.args[0]
        assert req.chunking_config is cfg
        assert req.collection_name == "col"

    @pytest.mark.asyncio
    async def test_query_params_ignored_when_clause_active(
        self, kb_repo, unified, dept_repo
    ):
        cfg = UploadChunkingConfig(strategy="clause_aware", params={}, display={})
        resolver = AsyncMock()
        resolver.resolve.return_value = cfg
        logger = MagicMock()
        uc = KnowledgeBaseUploadUseCase(
            kb_repo=kb_repo, policy=KnowledgeBasePolicy(),
            dept_repo=dept_repo, unified_upload=unified,
            logger=logger, chunking_resolver=resolver,
        )
        await uc.execute(
            "kb1", _user(), b"x", "f.pdf", "r",
            child_chunk_size=999, child_chunk_overlap=111,
        )
        logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_resolver_passes_none(self, kb_repo, unified, dept_repo):
        uc = KnowledgeBaseUploadUseCase(
            kb_repo=kb_repo, policy=KnowledgeBasePolicy(),
            dept_repo=dept_repo, unified_upload=unified, logger=MagicMock(),
        )
        await uc.execute("kb1", _user(), b"x", "f.pdf", "r")
        req = unified.execute.call_args.args[0]
        assert req.chunking_config is None
