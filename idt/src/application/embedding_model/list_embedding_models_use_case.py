from src.domain.embedding_model.entity import EmbeddingModel
from src.domain.embedding_model.interfaces import EmbeddingModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ListEmbeddingModelsUseCase:
    def __init__(
        self,
        repository: EmbeddingModelRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repo = repository
        self._logger = logger

    async def execute(self, request_id: str) -> list[EmbeddingModel]:
        self._logger.info(
            "list_embedding_models",
            request_id=request_id,
        )
        return await self._repo.list_active(request_id)
