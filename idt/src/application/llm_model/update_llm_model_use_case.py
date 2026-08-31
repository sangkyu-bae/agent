"""UpdateLlmModelUseCase: 기존 LLM 모델 수정."""
from datetime import datetime, timezone

from src.application.llm_model.schemas import (
    LlmModelResponse,
    UpdateLlmModelRequest,
)
from src.application.llm_model.cache_invalidation import (
    invalidate_llm_model_cache,
)
from src.domain.llm.interfaces import UtilityLLMProviderPort
from src.domain.llm_model.entity import LlmModel
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class UpdateLlmModelUseCase:
    def __init__(
        self,
        repository: LlmModelRepositoryInterface,
        logger: LoggerInterface,
        llm_provider: UtilityLLMProviderPort | None = None,
    ) -> None:
        self._repository = repository
        self._logger = logger
        # admin-default-llm-routing D-8: is_default 변경이 지나는 경로다.
        # 무효화 훅이 비어 있어 관리자 모델 교체가 반영되지 않았다.
        self._llm_provider = llm_provider

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

            _apply_field_updates(model, request)
            await self._apply_default_flag(model, request, request_id)

            model.updated_at = datetime.now(timezone.utc)
            updated = await self._repository.update(model, request_id)

            # ★ AD-3 의무 — 캡슐화로 빼먹기 불가
            await invalidate_llm_model_cache(
                self._llm_provider, self._logger, request_id, model_id
            )

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

    async def _apply_default_flag(
        self,
        model: LlmModel,
        request: UpdateLlmModelRequest,
        request_id: str,
    ) -> None:
        """is_default 토글. True 승격 시 기존 기본 모델을 먼저 해제한다.

        LlmModelPolicy.validate_single_default — 기본 모델은 전체에서 1개만
        허용되므로, 승격 전에 unset_all_defaults 를 호출해야 한다.
        """
        if request.is_default is True and not model.is_default:
            await self._repository.unset_all_defaults(request_id)
            model.is_default = True
        elif request.is_default is False:
            model.is_default = False


def _apply_field_updates(
    model: LlmModel, request: UpdateLlmModelRequest
) -> None:
    """None 이 아닌 필드만 부분 갱신한다 (PATCH 의미론)."""
    if request.display_name is not None:
        model.display_name = request.display_name
    if request.description is not None:
        model.description = request.description
    if request.max_tokens is not None:
        model.max_tokens = request.max_tokens
    if request.is_active is not None:
        model.is_active = request.is_active
    if request.base_url is not None:
        # 빈 문자열은 self-host 해제로 간주 → None 정규화 (R3).
        model.base_url = request.base_url or None
    if request.supports_vision is not None:
        model.supports_vision = request.supports_vision
