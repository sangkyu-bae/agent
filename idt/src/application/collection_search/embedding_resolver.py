"""컬렉션 임베딩 모델 해석 공용 헬퍼 (kb-retrieval-test D2).

activity_log의 CREATE 기록에서 embedding_model을 읽어 등록된 모델을 반환한다.
CollectionSearchUseCase와 KbSearchUseCase가 공유한다 — 로직 이중화 방지.
"""
from src.domain.collection.interfaces import ActivityLogRepositoryInterface
from src.domain.embedding_model.interfaces import (
    EmbeddingModelRepositoryInterface,
)


async def resolve_collection_embedding_model(
    collection_name: str,
    activity_log_repo: ActivityLogRepositoryInterface,
    embedding_model_repo: EmbeddingModelRepositoryInterface,
    request_id: str,
):
    logs = await activity_log_repo.find_all(
        request_id=request_id,
        collection_name=collection_name,
        action="CREATE",
        limit=1,
    )
    if not logs or not logs[0].detail:
        raise ValueError(
            f"Cannot determine embedding model for '{collection_name}'"
        )
    model_name = logs[0].detail.get("embedding_model")
    if not model_name:
        raise ValueError(
            f"Cannot determine embedding model for '{collection_name}'"
        )
    model = await embedding_model_repo.find_by_model_name(
        model_name, request_id
    )
    if model is None:
        raise ValueError(f"Embedding model '{model_name}' not registered")
    return model
