import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.application.embedding_model.list_embedding_models_use_case import (
    ListEmbeddingModelsUseCase,
)

router = APIRouter(
    prefix="/api/v1/embedding-models", tags=["Embedding Models"]
)


def get_list_embedding_models_use_case() -> ListEmbeddingModelsUseCase:
    raise NotImplementedError


class EmbeddingModelResponse(BaseModel):
    id: int
    provider: str
    model_name: str
    display_name: str
    vector_dimension: int
    description: str | None


class EmbeddingModelListResponse(BaseModel):
    models: list[EmbeddingModelResponse]
    total: int


@router.get("", response_model=EmbeddingModelListResponse)
async def list_embedding_models(
    use_case: ListEmbeddingModelsUseCase = Depends(
        get_list_embedding_models_use_case
    ),
):
    request_id = str(uuid.uuid4())
    models = await use_case.execute(request_id)
    return EmbeddingModelListResponse(
        models=[
            EmbeddingModelResponse(
                id=m.id,
                provider=m.provider,
                model_name=m.model_name,
                display_name=m.display_name,
                vector_dimension=m.vector_dimension,
                description=m.description,
            )
            for m in models
        ],
        total=len(models),
    )
