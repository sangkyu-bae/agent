"""AgentRun 도메인 정책.

AGENT-OBS-001 §2-3:
- RunStatusTransitionPolicy: RUNNING -> SUCCESS/FAILED/CANCELLED 만 허용
- CostCalculationPolicy: 가격 스냅샷 × 토큰 → CostUsd (정밀도 6자리)
"""
from decimal import Decimal
from typing import Optional

from src.domain.agent_run.value_objects import CostUsd, RunStatus, TokenUsage


class RunStatusTransitionPolicy:
    """Run 상태 전이 규칙: RUNNING -> SUCCESS/FAILED/CANCELLED 만 허용."""

    _ALLOWED: dict[RunStatus, set[RunStatus]] = {
        RunStatus.RUNNING: {RunStatus.SUCCESS, RunStatus.FAILED, RunStatus.CANCELLED},
        RunStatus.SUCCESS: set(),
        RunStatus.FAILED: set(),
        RunStatus.CANCELLED: set(),
    }

    @classmethod
    def can_transition(cls, current: RunStatus, target: RunStatus) -> bool:
        return target in cls._ALLOWED.get(current, set())

    @classmethod
    def ensure(cls, current: RunStatus, target: RunStatus) -> None:
        if not cls.can_transition(current, target):
            raise ValueError(
                f"Invalid run status transition: {current.value} -> {target.value}"
            )


class CostCalculationPolicy:
    """가격 스냅샷 × 토큰 → CostUsd. 가격이 None이면 0 비용 반환."""

    _QUANT = Decimal("0.000001")

    @staticmethod
    def compute(
        token_usage: TokenUsage,
        input_price_per_1k_usd: Optional[Decimal],
        output_price_per_1k_usd: Optional[Decimal],
    ) -> CostUsd:
        if input_price_per_1k_usd is None or output_price_per_1k_usd is None:
            return CostUsd()
        thousand = Decimal(1000)
        input_usd = (
            Decimal(token_usage.prompt_tokens) / thousand
        ) * input_price_per_1k_usd
        output_usd = (
            Decimal(token_usage.completion_tokens) / thousand
        ) * output_price_per_1k_usd
        input_q = input_usd.quantize(CostCalculationPolicy._QUANT)
        output_q = output_usd.quantize(CostCalculationPolicy._QUANT)
        total_q = (input_q + output_q).quantize(CostCalculationPolicy._QUANT)
        return CostUsd(input_usd=input_q, output_usd=output_q, total_usd=total_q)
