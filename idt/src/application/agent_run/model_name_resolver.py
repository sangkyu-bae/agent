"""LangChain model_name 문자열 → llm_model.id 매핑.

AGENT-OBS-001 §3-3 / §11 위험 요소:
매핑 실패 시 NULL FK + warning log. 매핑 실패해도 model_name은 ai_llm_call에
스냅샷 저장되어 사후 매핑 가능.
"""
from typing import Optional

from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class ModelNameResolver:
    """(provider, model_name) → llm_model.id 매핑.

    캐시 hit/miss 결과를 모두 캐시 (반복 미인식 모델로 인한 DB 조회 폭증 방지).
    """

    def __init__(
        self,
        llm_model_repo: LlmModelRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._repo = llm_model_repo
        self._logger = logger
        self._cache: dict[tuple[str, str], Optional[str]] = {}

    async def resolve(self, provider: str, model_name: str) -> Optional[str]:
        key = (provider, model_name)
        if key in self._cache:
            return self._cache[key]
        model = await self._repo.find_by_provider_and_name(
            provider, model_name, request_id="model-resolver"
        )
        result: Optional[str] = model.id if model else None
        if result is None:
            self._logger.warning(
                "LLM model not registered — ai_llm_call.llm_model_id will be NULL",
                provider=provider,
                model_name=model_name,
            )
        self._cache[key] = result
        return result

    def invalidate(self) -> None:
        """모델 등록 변경 시 호출."""
        self._cache.clear()
