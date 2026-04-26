from datetime import datetime, timezone

from src.domain.embedding_model.entity import EmbeddingModel


class TestEmbeddingModel:
    def test_create_embedding_model(self):
        now = datetime.now(timezone.utc)
        model = EmbeddingModel(
            id=1,
            provider="openai",
            model_name="text-embedding-3-small",
            display_name="OpenAI Embedding 3 Small",
            vector_dimension=1536,
            is_active=True,
            description="범용 임베딩 모델",
            created_at=now,
            updated_at=now,
        )
        assert model.id == 1
        assert model.provider == "openai"
        assert model.model_name == "text-embedding-3-small"
        assert model.display_name == "OpenAI Embedding 3 Small"
        assert model.vector_dimension == 1536
        assert model.is_active is True
        assert model.description == "범용 임베딩 모델"

    def test_create_with_none_description(self):
        now = datetime.now(timezone.utc)
        model = EmbeddingModel(
            id=2,
            provider="ollama",
            model_name="nomic-embed-text",
            display_name="Nomic Embed Text",
            vector_dimension=768,
            is_active=False,
            description=None,
            created_at=now,
            updated_at=now,
        )
        assert model.description is None
        assert model.is_active is False
