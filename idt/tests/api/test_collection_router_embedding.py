from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.collection_router import (
    router,
    get_collection_use_case,
    get_activity_log_service,
)


@pytest.fixture()
def mock_uc():
    uc = AsyncMock()
    return uc


@pytest.fixture()
def client(mock_uc):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_collection_use_case] = lambda: mock_uc
    app.dependency_overrides[get_activity_log_service] = lambda: AsyncMock()
    return TestClient(app)


class TestCreateCollectionWithEmbeddingModel:
    def test_embedding_model_only(self, client, mock_uc):
        resp = client.post(
            "/api/v1/collections",
            json={
                "name": "test-col",
                "embedding_model": "text-embedding-3-small",
                "distance": "Cosine",
            },
        )
        assert resp.status_code == 201

    def test_vector_size_only(self, client, mock_uc):
        resp = client.post(
            "/api/v1/collections",
            json={"name": "test-col", "vector_size": 1536, "distance": "Cosine"},
        )
        assert resp.status_code == 201

    def test_both_missing_returns_422(self, client):
        resp = client.post(
            "/api/v1/collections",
            json={"name": "test-col", "distance": "Cosine"},
        )
        assert resp.status_code == 422

    def test_both_provided(self, client, mock_uc):
        resp = client.post(
            "/api/v1/collections",
            json={
                "name": "test-col",
                "vector_size": 768,
                "embedding_model": "text-embedding-3-small",
                "distance": "Cosine",
            },
        )
        assert resp.status_code == 201
