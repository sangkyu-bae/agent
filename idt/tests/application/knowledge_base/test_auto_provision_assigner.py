"""AutoProvisionCollectionAssigner — agent-kb-quick-setup Design §9.4 / FR-02, FR-03."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.application.knowledge_base.collection_assigner import (
    AutoProvisionCollectionAssigner,
)
from src.domain.auth.entities import User, UserRole, UserStatus
from src.domain.collection.permission_schemas import CollectionScope
from src.domain.collection.schemas import DistanceMetric
from src.domain.embedding_model.entity import EmbeddingModel
from src.domain.kb_default_setting.errors import KbDefaultsNotConfiguredError

KB_ID = "3f1a9c2e-aaaa-bbbb-cccc-dddddddddddd"


def _user(user_id: int = 1) -> User:
    return User(
        email="u@test.com",
        password_hash="h",
        role=UserRole.USER,
        status=UserStatus.APPROVED,
        id=user_id,
    )


def _model() -> EmbeddingModel:
    now = datetime.now(UTC)
    return EmbeddingModel(
        id=2,
        provider="openai",
        model_name="text-embedding-3-small",
        display_name="small",
        vector_dimension=1536,
        is_active=True,
        description=None,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def fallback() -> AsyncMock:
    a = AsyncMock()
    a.assign.return_value = "shared-col"
    return a


@pytest.fixture
def defaults() -> AsyncMock:
    d = AsyncMock()
    d.resolve_default_model.return_value = _model()
    return d


@pytest.fixture
def collection_uc() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def assigner(fallback, defaults, collection_uc) -> AutoProvisionCollectionAssigner:
    return AutoProvisionCollectionAssigner(
        fallback=fallback,
        defaults=defaults,
        collection_use_case=collection_uc,
        logger=MagicMock(),
    )


class TestDelegation:
    async def test_requested_collection_goes_to_fallback(
        self, assigner, fallback, collection_uc
    ):
        result = await assigner.assign(_user(), "shared-col", "req", kb_id=KB_ID)
        assert result == "shared-col"
        fallback.assign.assert_awaited_once()
        collection_uc.create_collection.assert_not_awaited()


class TestAutoProvision:
    async def test_creates_collection_with_default_model(
        self, assigner, collection_uc
    ):
        name = await assigner.assign(
            _user(),
            None,
            "req",
            kb_id=KB_ID,
            scope=CollectionScope.DEPARTMENT,
            department_id="d1",
        )
        assert name == "kb-3f1a9c2e"
        call = collection_uc.create_collection.await_args
        req = call.args[0]
        assert req.name == "kb-3f1a9c2e"
        assert req.vector_size == 1536
        assert req.embedding_model == "text-embedding-3-small"
        assert req.distance == DistanceMetric.COSINE
        assert call.kwargs["scope"] == CollectionScope.DEPARTMENT
        assert call.kwargs["department_id"] == "d1"
        assert call.kwargs["user"].id == 1

    async def test_requires_kb_id(self, assigner):
        with pytest.raises(ValueError, match="kb_id"):
            await assigner.assign(_user(), None, "req")

    async def test_unconfigured_defaults_propagate(
        self, assigner, defaults, collection_uc
    ):
        defaults.resolve_default_model.side_effect = KbDefaultsNotConfiguredError()
        with pytest.raises(KbDefaultsNotConfiguredError):
            await assigner.assign(
                _user(), None, "req", kb_id=KB_ID, scope=CollectionScope.PERSONAL
            )
        collection_uc.create_collection.assert_not_awaited()

    async def test_existing_collection_conflict_propagates(
        self, assigner, collection_uc
    ):
        collection_uc.create_collection.side_effect = ValueError(
            "Collection 'kb-3f1a9c2e' already exists"
        )
        with pytest.raises(ValueError, match="already exists"):
            await assigner.assign(
                _user(), None, "req", kb_id=KB_ID, scope=CollectionScope.PERSONAL
            )


class TestRollback:
    async def test_rollback_deletes_auto_collection_best_effort(
        self, assigner, collection_uc
    ):
        await assigner.rollback("kb-3f1a9c2e", _user(), "req")
        collection_uc.delete_collection.assert_awaited_once()
        assert collection_uc.delete_collection.await_args.args[0] == "kb-3f1a9c2e"

    async def test_rollback_swallows_delete_failure(self, assigner, collection_uc):
        collection_uc.delete_collection.side_effect = RuntimeError("qdrant down")
        await assigner.rollback("kb-3f1a9c2e", _user(), "req")  # no raise

    async def test_rollback_ignores_non_auto_names(self, assigner, collection_uc):
        """사용자가 고른 공유 컬렉션은 절대 지우지 않는다."""
        await assigner.rollback("shared-col", _user(), "req")
        collection_uc.delete_collection.assert_not_awaited()
