"""CostCalculator: llm_model 가격 TTL 캐시 + 토큰×가격 → CostUsd.

AGENT-OBS-001 §3-2 / §14-6:
- TTL 5분 기본
- PATCH /llm-models/{id}/pricing 시 invalidate() 호출 의무
- 가격 None이면 0 비용 반환
- monotonic clock 사용 (테스트 시 주입 가능)
"""
import time
from decimal import Decimal
from typing import Callable, Optional

from src.application.agent_run.schemas import RunObservabilityConfig
from src.domain.agent_run.policies import CostCalculationPolicy
from src.domain.agent_run.value_objects import CostUsd, TokenUsage
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface


class CostCalculator:
    """가격 캐시 + 비용 계산."""

    def __init__(
        self,
        llm_model_repo: LlmModelRepositoryInterface,
        config: RunObservabilityConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._repo = llm_model_repo
        self._ttl = config.pricing_cache_ttl_seconds
        self._clock = clock
        # cache: llm_model_id -> ((input_price, output_price), expires_at)
        self._cache: dict[
            str, tuple[tuple[Optional[Decimal], Optional[Decimal]], float]
        ] = {}

    async def get_pricing(
        self, llm_model_id: str
    ) -> tuple[Optional[Decimal], Optional[Decimal]]:
        now = self._clock()
        cached = self._cache.get(llm_model_id)
        if cached is not None and cached[1] > now:
            return cached[0]
        model = await self._repo.find_by_id(llm_model_id, request_id="cost-calc")
        if model is None:
            result: tuple[Optional[Decimal], Optional[Decimal]] = (None, None)
        else:
            result = (model.input_price_per_1k_usd, model.output_price_per_1k_usd)
        self._cache[llm_model_id] = (result, now + self._ttl)
        return result

    def invalidate(self, llm_model_id: Optional[str] = None) -> None:
        """관리자 가격 변경 API에서 호출 의무.

        Args:
            llm_model_id: None이면 전체 캐시 비움, 아니면 해당 모델만.
        """
        if llm_model_id is None:
            self._cache.clear()
        else:
            self._cache.pop(llm_model_id, None)

    def compute(
        self,
        token_usage: TokenUsage,
        input_price: Optional[Decimal],
        output_price: Optional[Decimal],
    ) -> CostUsd:
        return CostCalculationPolicy.compute(token_usage, input_price, output_price)
