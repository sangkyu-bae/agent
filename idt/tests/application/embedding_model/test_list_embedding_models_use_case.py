from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.embedding_model.list_embedding_models_use_case import (
    ListEmbeddingModelsUseCase,
)
from src.domain.embedding_model.entity import EmbeddingModel


def _model(model_name: str = "text-embedding-3-small", is_active: bool = True) -> EmbeddingModel:
    now = datetime.now(timezone.utc)
    return EmbeddingModel(
        id=1,
        provider="openai",
        model_name=model_name,
        display_name=model_name,
        vector_dimension=1536,
        is_active=is_active,
        description=None,
        created_at=now,
        updated_at=now,
    )


class TestListEmbeddingModelsUseCase:
    @pytest.fixture()
    def repo(self):
        return AsyncMock()

    @pytest.fixture()
    def logger(self):
        return MagicMock()

    @pytest.fixture()
    def use_case(self, repo, logger):
        return ListEmbeddingModelsUseCase(repository=repo, logger=logger)

    async def test_returns_active_models(self, use_case, repo):
        models = [_model("m1"), _model("m2")]
        repo.list_active.return_value = models
        result = await use_case.execute("req-1")
        assert len(result) == 2
        repo.list_active.assert_awaited_once_with("req-1")

    async def test_returns_empty_list(self, use_case, repo):
        repo.list_active.return_value = []
        result = await use_case.execute("req-2")
        assert result == []
