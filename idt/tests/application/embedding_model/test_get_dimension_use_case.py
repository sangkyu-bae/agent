from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.embedding_model.get_dimension_use_case import (
    GetDimensionUseCase,
)
from src.domain.embedding_model.entity import EmbeddingModel


def _model(
    model_name: str = "text-embedding-3-small",
    vector_dimension: int = 1536,
    is_active: bool = True,
) -> EmbeddingModel:
    now = datetime.now(timezone.utc)
    return EmbeddingModel(
        id=1,
        provider="openai",
        model_name=model_name,
        display_name=model_name,
        vector_dimension=vector_dimension,
        is_active=is_active,
        description=None,
        created_at=now,
        updated_at=now,
    )


class TestGetDimensionUseCase:
    @pytest.fixture()
    def repo(self):
        return AsyncMock()

    @pytest.fixture()
    def logger(self):
        return MagicMock()

    @pytest.fixture()
    def use_case(self, repo, logger):
        return GetDimensionUseCase(repository=repo, logger=logger)

    async def test_returns_dimension(self, use_case, repo):
        repo.find_by_model_name.return_value = _model(vector_dimension=3072)
        result = await use_case.execute("text-embedding-3-large", "req-1")
        assert result == 3072

    async def test_unknown_model_raises(self, use_case, repo):
        repo.find_by_model_name.return_value = None
        with pytest.raises(ValueError, match="Unknown embedding model"):
            await use_case.execute("nonexistent", "req-2")

    async def test_deactivated_model_raises(self, use_case, repo):
        repo.find_by_model_name.return_value = _model(is_active=False)
        with pytest.raises(ValueError, match="deactivated"):
            await use_case.execute("text-embedding-3-small", "req-3")
