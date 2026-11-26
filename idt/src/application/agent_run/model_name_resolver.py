"""LangChain model_name 문자열 → llm_model.id 매핑.

AGENT-OBS-001 §3-3 / §11 위험 요소:
매핑 실패 시 NULL FK + warning log. 매핑 실패해도 model_name은 ai_llm_call에
스냅샷 저장되어 사후 매핑 가능.

공급사 응답의 모델명은 날짜 붙은 스냅샷명일 수 있다(gpt-5.1-2025-11-13,
claude-3-5-sonnet-20241022). 정확한 이름이 없으면 날짜 꼬리를 뗀 기본명으로
한 번 더 찾는다 — 없으면 단가를 못 찾아 비용이 0 으로 남는다.
"""
import re

from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_DATE_SUFFIX = re.compile(r"-(?:\d{4}-\d{2}-\d{2}|\d{8})$")


def base_model_name(model_name: str) -> str | None:
    """날짜 꼬리(-YYYY-MM-DD / -YYYYMMDD)를 뗀 이름. 꼬리가 없으면 None."""
    stripped = _DATE_SUFFIX.sub("", model_name)
    return stripped if stripped != model_name and stripped else None


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
        self._cache: dict[tuple[str, str], str | None] = {}

    async def resolve(self, provider: str, model_name: str) -> str | None:
        key = (provider, model_name)
        if key in self._cache:
            return self._cache[key]
        result: str | None = None
        for name in (model_name, base_model_name(model_name)):
            if name is None:
                continue
            model = await self._repo.find_by_provider_and_name(
                provider, name, request_id="model-resolver"
            )
            if model is not None:
                result = model.id
                break
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
