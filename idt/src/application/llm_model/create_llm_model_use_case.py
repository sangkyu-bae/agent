"""CreateLlmModelUseCase: 신규 LLM 모델 등록."""
import uuid
from datetime import datetime, timezone

from src.application.llm_model.schemas import (
    CreateLlmModelRequest,
    LlmModelResponse,
)
from src.application.llm_model.cache_invalidation import (
    invalidate_llm_model_cache,
)
from src.domain.llm.interfaces import UtilityLLMProviderPort
from src.domain.llm_model.entity import LlmModel
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.llm_model.policies import LlmModelPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class CreateLlmModelUseCase:
    def __init__(
        self,
        repository: LlmModelRepositoryInterface,
        logger: LoggerInterface,
        llm_provider: UtilityLLMProviderPort | None = None,
    ) -> None:
        self._repository = repository
        self._logger = logger
        self._llm_provider = llm_provider

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
            await self._reject_duplicate(request, request_id)

            if request.is_default:
                # 기본 모델은 전체에서 1개만 허용된다 (LlmModelPolicy).
                await self._repository.unset_all_defaults(request_id)

            saved = await self._repository.save(_build_model(request), request_id)

            # ★ AD-3 의무 — is_default=True 등록은 기존 기본 모델을 밀어낸다.
            await invalidate_llm_model_cache(
                self._llm_provider, self._logger, request_id, saved.id
            )

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

    async def _reject_duplicate(
        self, request: CreateLlmModelRequest, request_id: str
    ) -> None:
        """(provider, model_name) 중복 등록을 막는다."""
        existing = await self._repository.find_by_provider_and_name(
            request.provider, request.model_name, request_id
        )
        if existing is not None:
            raise ValueError(
                f"이미 등록된 모델입니다: {request.provider}/{request.model_name}"
            )


def _build_model(request: CreateLlmModelRequest) -> LlmModel:
    """등록 요청 → 신규 LlmModel 엔티티."""
    now = datetime.now(timezone.utc)
    return LlmModel(
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
        # 빈 문자열은 self-host 미사용으로 간주 → None 정규화.
        base_url=request.base_url or None,
        supports_vision=request.supports_vision,
    )
