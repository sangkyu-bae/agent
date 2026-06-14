"""UpdateLlmModelPricingUseCase: LLM 모델 가격 변경 + 캐시 무효화 (M4 / M1 G1).

agent-run-observability-m4 Design §3.4.

★ 핵심: `cost_calculator.invalidate(model_id)` 의무 호출을 use case 안에 캡슐화
   → router/테스트가 빼먹어도 단위 테스트가 강제 검증.
"""
from datetime import datetime, timezone

from src.application.agent_run.cost_calculator import CostCalculator
from src.application.llm_model.schemas import (
    LlmModelResponse,
    UpdatePricingRequest,
)
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class UpdateLlmModelPricingUseCase:
    """관리자가 가격을 변경한다. 변경 직후 가격 캐시를 무효화한다."""

    def __init__(
        self,
        repository: LlmModelRepositoryInterface,
        cost_calculator: CostCalculator,
        logger: LoggerInterface,
    ) -> None:
        self._repo = repository
        self._cost_calc = cost_calculator
        self._logger = logger

    async def execute(
        self,
        model_id: str,
        request: UpdatePricingRequest,
        request_id: str,
    ) -> LlmModelResponse:
        self._logger.info(
            "UpdateLlmModelPricingUseCase start",
            request_id=request_id,
            model_id=model_id,
        )

        model = await self._repo.find_by_id(model_id, request_id)
        if model is None:
            raise ValueError(f"모델을 찾을 수 없습니다: {model_id}")

        now = datetime.now(timezone.utc)
        model.input_price_per_1k_usd = request.input_price_per_1k_usd
        model.output_price_per_1k_usd = request.output_price_per_1k_usd
        model.pricing_updated_at = now
        model.updated_at = now

        updated = await self._repo.update(model, request_id)

        # ★ M1 G1 의무 — 캡슐화로 빼먹기 불가
        self._cost_calc.invalidate(model_id)

        self._logger.info(
            "LLM pricing updated and cache invalidated",
            request_id=request_id,
            model_id=model_id,
            input_price=str(request.input_price_per_1k_usd),
            output_price=str(request.output_price_per_1k_usd),
        )
        return LlmModelResponse.from_domain(updated)
