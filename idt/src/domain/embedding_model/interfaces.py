from abc import ABC, abstractmethod

from src.domain.embedding_model.entity import EmbeddingModel


class EmbeddingModelRepositoryInterface(ABC):
    @abstractmethod
    async def find_by_model_name(
        self, model_name: str, request_id: str
    ) -> EmbeddingModel | None: ...

    @abstractmethod
    async def list_active(
        self, request_id: str
    ) -> list[EmbeddingModel]: ...

    @abstractmethod
    async def save(
        self, model: EmbeddingModel, request_id: str
    ) -> EmbeddingModel: ...

    @abstractmethod
    async def find_by_provider_and_name(
        self, provider: str, model_name: str, request_id: str
    ) -> EmbeddingModel | None: ...
