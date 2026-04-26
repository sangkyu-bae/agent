from src.domain.embedding_model.interfaces import EmbeddingModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class GetDimensionUseCase:
    def __init__(
        self,
        repository: EmbeddingModelRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repo = repository
        self._logger = logger

    async def execute(
        self, model_name: str, request_id: str
    ) -> int:
        model = await self._repo.find_by_model_name(model_name, request_id)
        if model is None:
            raise ValueError(
                f"Unknown embedding model: '{model_name}'"
            )
        if not model.is_active:
            raise ValueError(
                f"Embedding model '{model_name}' is deactivated"
            )
        self._logger.info(
            "get_dimension resolved",
            request_id=request_id,
            model_name=model_name,
            vector_dimension=model.vector_dimension,
        )
        return model.vector_dimension
