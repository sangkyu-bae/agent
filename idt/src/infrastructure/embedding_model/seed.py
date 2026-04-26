from datetime import datetime, timezone

from src.domain.embedding_model.entity import EmbeddingModel
from src.domain.embedding_model.interfaces import (
    EmbeddingModelRepositoryInterface,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


DEFAULT_EMBEDDING_MODELS: list[dict] = [
    {
        "provider": "openai",
        "model_name": "text-embedding-3-small",
        "display_name": "OpenAI Embedding 3 Small",
        "vector_dimension": 1536,
        "description": "가성비 좋은 범용 임베딩 모델",
    },
    {
        "provider": "openai",
        "model_name": "text-embedding-3-large",
        "display_name": "OpenAI Embedding 3 Large",
        "vector_dimension": 3072,
        "description": "고품질 임베딩 모델 (정확도 우선)",
    },
    {
        "provider": "openai",
        "model_name": "text-embedding-ada-002",
        "display_name": "OpenAI Ada 002",
        "vector_dimension": 1536,
        "description": "이전 세대 범용 임베딩 모델",
    },
]


async def seed_default_embedding_models(
    repository: EmbeddingModelRepositoryInterface,
    logger: LoggerInterface,
    request_id: str,
) -> None:
    logger.info("seed_default_embedding_models start", request_id=request_id)
    now = datetime.now(timezone.utc)
    for spec in DEFAULT_EMBEDDING_MODELS:
        existing = await repository.find_by_provider_and_name(
            spec["provider"], spec["model_name"], request_id
        )
        if existing is not None:
            continue
        model = EmbeddingModel(
            id=0,
            provider=spec["provider"],
            model_name=spec["model_name"],
            display_name=spec["display_name"],
            vector_dimension=spec["vector_dimension"],
            is_active=True,
            description=spec.get("description"),
            created_at=now,
            updated_at=now,
        )
        await repository.save(model, request_id)
    logger.info("seed_default_embedding_models done", request_id=request_id)
