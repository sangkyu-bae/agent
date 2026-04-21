"""GetLlmModelUseCase: 단일 LLM 모델 조회."""
from src.application.llm_model.schemas import LlmModelResponse
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class GetLlmModelUseCase:
    def __init__(
        self,
        repository: LlmModelRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(self, model_id: str, request_id: str) -> LlmModelResponse:
        self._logger.info(
            "GetLlmModelUseCase start",
            request_id=request_id,
            model_id=model_id,
        )
        try:
            model = await self._repository.find_by_id(model_id, request_id)
            if model is None:
                raise ValueError(f"모델을 찾을 수 없습니다: {model_id}")
            self._logger.info(
                "GetLlmModelUseCase done",
                request_id=request_id,
                model_id=model_id,
            )
            return LlmModelResponse.from_domain(model)
        except Exception as e:
            self._logger.error(
                "GetLlmModelUseCase failed", exception=e, request_id=request_id
            )
            raise
