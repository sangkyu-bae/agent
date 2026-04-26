from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.collection.use_case import CollectionManagementUseCase
from src.domain.collection.schemas import CreateCollectionRequest, DistanceMetric
from src.domain.embedding_model.entity import EmbeddingModel


def _emb_model(
    model_name: str = "text-embedding-3-small",
    vector_dimension: int = 1536,
) -> EmbeddingModel:
    now = datetime.now(timezone.utc)
    return EmbeddingModel(
        id=1,
        provider="openai",
        model_name=model_name,
        display_name=model_name,
        vector_dimension=vector_dimension,
        is_active=True,
        description=None,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture()
def deps():
    repo = AsyncMock()
    repo.collection_exists.return_value = False
    policy = MagicMock()
    activity_log = AsyncMock()
    embedding_model_repo = AsyncMock()
    uc = CollectionManagementUseCase(
        repository=repo,
        policy=policy,
        activity_log=activity_log,
        default_collection="default",
        embedding_model_repo=embedding_model_repo,
    )
    return uc, repo, embedding_model_repo


class TestCreateCollectionWithEmbeddingModel:
    async def test_embedding_model_auto_dimension(self, deps):
        uc, repo, emb_repo = deps
        emb_repo.find_by_model_name.return_value = _emb_model(
            vector_dimension=3072
        )
        req = CreateCollectionRequest(
            name="test-col",
            vector_size=0,
            distance=DistanceMetric.COSINE,
            embedding_model="text-embedding-3-large",
        )
        await uc.create_collection(req, "req-1")
        actual = repo.create_collection.call_args[0][0]
        assert actual.vector_size == 3072

    async def test_vector_size_direct(self, deps):
        uc, repo, emb_repo = deps
        req = CreateCollectionRequest(
            name="test-col",
            vector_size=1536,
            distance=DistanceMetric.COSINE,
        )
        await uc.create_collection(req, "req-2")
        actual = repo.create_collection.call_args[0][0]
        assert actual.vector_size == 1536
        emb_repo.find_by_model_name.assert_not_awaited()

    async def test_unknown_embedding_model_raises(self, deps):
        uc, repo, emb_repo = deps
        emb_repo.find_by_model_name.return_value = None
        req = CreateCollectionRequest(
            name="test-col",
            vector_size=0,
            distance=DistanceMetric.COSINE,
            embedding_model="nonexistent",
        )
        with pytest.raises(ValueError, match="Unknown embedding model"):
            await uc.create_collection(req, "req-3")
