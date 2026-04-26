from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.embedding_model_router import (
    router,
    get_list_embedding_models_use_case,
)
from src.domain.embedding_model.entity import EmbeddingModel


def _model(model_name: str, dim: int) -> EmbeddingModel:
    now = datetime.now(timezone.utc)
    return EmbeddingModel(
        id=1,
        provider="openai",
        model_name=model_name,
        display_name=model_name,
        vector_dimension=dim,
        is_active=True,
        description="test",
        created_at=now,
        updated_at=now,
    )


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(router)

    mock_uc = AsyncMock()
    mock_uc.execute.return_value = [
        _model("text-embedding-3-small", 1536),
        _model("text-embedding-3-large", 3072),
    ]
    app.dependency_overrides[get_list_embedding_models_use_case] = lambda: mock_uc

    return TestClient(app)


class TestListEmbeddingModelsEndpoint:
    def test_list_returns_200(self, client):
        resp = client.get("/api/v1/embedding-models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["models"][0]["model_name"] == "text-embedding-3-small"
        assert data["models"][1]["vector_dimension"] == 3072
