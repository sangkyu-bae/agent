"""ListLlmModelsUseCase: LLM 모델 목록 조회."""
from src.application.llm_model.schemas import (
    LlmModelListResponse,
    LlmModelResponse,
)
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ListLlmModelsUseCase:
    def __init__(
        self,
        repository: LlmModelRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(
        self, include_inactive: bool, request_id: str
    ) -> LlmModelListResponse:
        self._logger.info(
            "ListLlmModelsUseCase start",
            request_id=request_id,
            include_inactive=include_inactive,
        )
        try:
            if include_inactive:
                models = await self._repository.list_all(request_id)
            else:
                models = await self._repository.list_active(request_id)
            self._logger.info(
                "ListLlmModelsUseCase done",
                request_id=request_id,
                count=len(models),
            )
            return LlmModelListResponse(
                models=[LlmModelResponse.from_domain(m) for m in models]
            )
        except Exception as e:
            self._logger.error(
                "ListLlmModelsUseCase failed",
                exception=e,
                request_id=request_id,
            )
            raise
