"""UpdateLlmModelUseCase: 기존 LLM 모델 수정."""
from datetime import datetime, timezone

from src.application.llm_model.schemas import (
    LlmModelResponse,
    UpdateLlmModelRequest,
)
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class UpdateLlmModelUseCase:
    def __init__(
        self,
        repository: LlmModelRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(
        self,
        model_id: str,
        request: UpdateLlmModelRequest,
        request_id: str,
    ) -> LlmModelResponse:
        self._logger.info(
            "UpdateLlmModelUseCase start",
            request_id=request_id,
            model_id=model_id,
        )
        try:
            model = await self._repository.find_by_id(model_id, request_id)
            if model is None:
                raise ValueError(f"모델을 찾을 수 없습니다: {model_id}")

            if request.display_name is not None:
                model.display_name = request.display_name
            if request.description is not None:
                model.description = request.description
            if request.max_tokens is not None:
                model.max_tokens = request.max_tokens
            if request.is_active is not None:
                model.is_active = request.is_active

            if request.is_default is True and not model.is_default:
                await self._repository.unset_all_defaults(request_id)
                model.is_default = True
            elif request.is_default is False:
                model.is_default = False

            model.updated_at = datetime.now(timezone.utc)
            updated = await self._repository.update(model, request_id)

            self._logger.info(
                "UpdateLlmModelUseCase done",
                request_id=request_id,
                model_id=model_id,
            )
            return LlmModelResponse.from_domain(updated)
        except Exception as e:
            self._logger.error(
                "UpdateLlmModelUseCase failed", exception=e, request_id=request_id
            )
            raise
