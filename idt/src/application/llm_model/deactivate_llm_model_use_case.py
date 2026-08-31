"""DeactivateLlmModelUseCase: LLM 모델 비활성화 (소프트 삭제)."""
from datetime import datetime, timezone

from src.application.llm_model.schemas import LlmModelResponse
from src.application.llm_model.cache_invalidation import (
    invalidate_llm_model_cache,
)
from src.domain.llm.interfaces import UtilityLLMProviderPort
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class DeactivateLlmModelUseCase:
    def __init__(
        self,
        repository: LlmModelRepositoryInterface,
        logger: LoggerInterface,
        llm_provider: UtilityLLMProviderPort | None = None,
    ) -> None:
        self._repository = repository
        self._logger = logger
        self._llm_provider = llm_provider

    async def execute(self, model_id: str, request_id: str) -> LlmModelResponse:
        self._logger.info(
            "DeactivateLlmModelUseCase start",
            request_id=request_id,
            model_id=model_id,
        )
        try:
            model = await self._repository.find_by_id(model_id, request_id)
            if model is None:
                raise ValueError(f"모델을 찾을 수 없습니다: {model_id}")

            model.is_active = False
            model.is_default = False
            model.updated_at = datetime.now(timezone.utc)
            updated = await self._repository.update(model, request_id)

            # ★ AD-3 의무 — 비활성 모델이 캐시에 남아 계속 쓰이면 안 된다.
            await invalidate_llm_model_cache(
                self._llm_provider, self._logger, request_id, model_id
            )

            self._logger.info(
                "DeactivateLlmModelUseCase done",
                request_id=request_id,
                model_id=model_id,
            )
            return LlmModelResponse.from_domain(updated)
        except Exception as e:
            self._logger.error(
                "DeactivateLlmModelUseCase failed",
                exception=e,
                request_id=request_id,
            )
            raise
