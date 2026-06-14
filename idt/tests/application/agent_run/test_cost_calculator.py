"""CostCalculator: TTL 캐시 + 비용 계산 검증."""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_run.cost_calculator import CostCalculator
from src.application.agent_run.schemas import RunObservabilityConfig
from src.domain.agent_run.value_objects import CostUsd, TokenUsage
from src.domain.llm_model.entity import LlmModel


def _make_model(
    model_id: str = "m-1",
    input_price: Decimal | None = Decimal("0.005"),
    output_price: Decimal | None = Decimal("0.015"),
) -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id=model_id,
        provider="openai",
        model_name="gpt-4o",
        display_name="GPT-4o",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=None,
        is_active=True,
        is_default=False,
        created_at=now,
        updated_at=now,
        input_price_per_1k_usd=input_price,
        output_price_per_1k_usd=output_price,
        pricing_updated_at=now,
    )


class ManualClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestGetPricing:
    @pytest.mark.asyncio
    async def test_first_call_hits_repo(self) -> None:
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=_make_model())
        clock = ManualClock()
        calc = CostCalculator(
            repo, RunObservabilityConfig(pricing_cache_ttl_seconds=300), clock=clock
        )

        input_p, output_p = await calc.get_pricing("m-1")

        repo.find_by_id.assert_awaited_once()
        assert input_p == Decimal("0.005")
        assert output_p == Decimal("0.015")

    @pytest.mark.asyncio
    async def test_second_call_within_ttl_uses_cache(self) -> None:
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=_make_model())
        clock = ManualClock()
        calc = CostCalculator(
            repo, RunObservabilityConfig(pricing_cache_ttl_seconds=300), clock=clock
        )

        await calc.get_pricing("m-1")
        clock.advance(299)
        await calc.get_pricing("m-1")

        assert repo.find_by_id.await_count == 1

    @pytest.mark.asyncio
    async def test_call_after_ttl_reloads(self) -> None:
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=_make_model())
        clock = ManualClock()
        calc = CostCalculator(
            repo, RunObservabilityConfig(pricing_cache_ttl_seconds=300), clock=clock
        )

        await calc.get_pricing("m-1")
        clock.advance(301)
        await calc.get_pricing("m-1")

        assert repo.find_by_id.await_count == 2

    @pytest.mark.asyncio
    async def test_unknown_model_returns_none(self) -> None:
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=None)
        calc = CostCalculator(repo, RunObservabilityConfig())

        result = await calc.get_pricing("missing")

        assert result == (None, None)


class TestInvalidate:
    @pytest.mark.asyncio
    async def test_invalidate_single_model_forces_reload(self) -> None:
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=_make_model())
        clock = ManualClock()
        calc = CostCalculator(
            repo, RunObservabilityConfig(pricing_cache_ttl_seconds=300), clock=clock
        )

        await calc.get_pricing("m-1")
        calc.invalidate("m-1")
        await calc.get_pricing("m-1")

        assert repo.find_by_id.await_count == 2

    @pytest.mark.asyncio
    async def test_invalidate_all_clears_cache(self) -> None:
        repo = MagicMock()
        repo.find_by_id = AsyncMock(return_value=_make_model())
        calc = CostCalculator(repo, RunObservabilityConfig())

        await calc.get_pricing("m-1")
        await calc.get_pricing("m-2")
        calc.invalidate()  # all
        await calc.get_pricing("m-1")
        await calc.get_pricing("m-2")

        assert repo.find_by_id.await_count == 4


class TestCompute:
    def test_compute_delegates_to_policy(self) -> None:
        calc = CostCalculator(MagicMock(), RunObservabilityConfig())
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=1000, total_tokens=2000)

        cost = calc.compute(usage, Decimal("0.005"), Decimal("0.015"))

        assert cost == CostUsd(
            input_usd=Decimal("0.005000"),
            output_usd=Decimal("0.015000"),
            total_usd=Decimal("0.020000"),
        )
