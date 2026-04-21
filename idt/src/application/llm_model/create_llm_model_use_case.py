"""CreateLlmModelUseCase: 신규 LLM 모델 등록."""
import uuid
from datetime import datetime, timezone

from src.application.llm_model.schemas import (
    CreateLlmModelRequest,
    LlmModelResponse,
)
from src.domain.llm_model.entity import LlmModel
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.llm_model.policies import LlmModelPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class CreateLlmModelUseCase:
    def __init__(
        self,
        repository: LlmModelRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repository = repository
        self._logger = logger

    async def execute(
        self, request: CreateLlmModelRequest, request_id: str
    ) -> LlmModelResponse:
        self._logger.info(
            "CreateLlmModelUseCase start",
            request_id=request_id,
            provider=request.provider,
            model_name=request.model_name,
        )
        try:
            LlmModelPolicy.validate_model_name_not_empty(request.model_name)

            existing = await self._repository.find_by_provider_and_name(
                request.provider, request.model_name, request_id
            )
            if existing is not None:
                raise ValueError(
                    f"이미 등록된 모델입니다: {request.provider}/{request.model_name}"
                )

            if request.is_default:
                await self._repository.unset_all_defaults(request_id)

            now = datetime.now(timezone.utc)
            model = LlmModel(
                id=str(uuid.uuid4()),
                provider=request.provider,
                model_name=request.model_name,
                display_name=request.display_name,
                description=request.description,
                api_key_env=request.api_key_env,
                max_tokens=request.max_tokens,
                is_active=request.is_active,
                is_default=request.is_default,
                created_at=now,
                updated_at=now,
            )
            saved = await self._repository.save(model, request_id)
            self._logger.info(
                "CreateLlmModelUseCase done",
                request_id=request_id,
                model_id=saved.id,
            )
            return LlmModelResponse.from_domain(saved)
        except Exception as e:
            self._logger.error(
                "CreateLlmModelUseCase failed", exception=e, request_id=request_id
            )
            raise
