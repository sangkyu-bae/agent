"""M4-7: UpdateLlmModelPricingUseCase 단위 테스트 (★ M1 G1).

핵심: cost_calculator.invalidate(model_id) 의무 호출이 캡슐화되어 있는지 검증.
"""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.llm_model.schemas import UpdatePricingRequest
from src.application.llm_model.update_llm_model_pricing_use_case import (
    UpdateLlmModelPricingUseCase,
)
from src.domain.llm_model.entity import LlmModel


def _make_model(model_id: str = "m-1") -> LlmModel:
    now = datetime.now(timezone.utc)
    return LlmModel(
        id=model_id,
        provider="openai",
        model_name="gpt-4o",
        display_name="GPT-4o",
        description=None,
        api_key_env="OPENAI_API_KEY",
        max_tokens=128000,
        is_active=True,
        is_default=False,
        created_at=now,
        updated_at=now,
        input_price_per_1k_usd=Decimal("0.001"),
        output_price_per_1k_usd=Decimal("0.002"),
        pricing_updated_at=now,
    )


def _make_use_case(model: LlmModel | None):
    repo = MagicMock()
    repo.find_by_id = AsyncMock(return_value=model)
    repo.update = AsyncMock(side_effect=lambda m, _: m)

    cost_calc = MagicMock()
    cost_calc.invalidate = MagicMock()

    logger = MagicMock()
    uc = UpdateLlmModelPricingUseCase(
        repository=repo,
        cost_calculator=cost_calc,
        logger=logger,
    )
    return uc, repo, cost_calc, logger


class TestUpdatePricing:
    @pytest.mark.asyncio
    async def test_updates_pricing_columns(self):
        model = _make_model()
        uc, repo, _, _ = _make_use_case(model)
        req = UpdatePricingRequest(
            input_price_per_1k_usd=Decimal("0.005"),
            output_price_per_1k_usd=Decimal("0.015"),
        )

        response = await uc.execute("m-1", req, request_id="req-1")

        assert response.input_price_per_1k_usd == Decimal("0.005")
        assert response.output_price_per_1k_usd == Decimal("0.015")
        repo.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sets_pricing_updated_at_to_now(self):
        model = _make_model()
        old_ts = model.pricing_updated_at
        uc, repo, _, _ = _make_use_case(model)
        req = UpdatePricingRequest(
            input_price_per_1k_usd=Decimal("0.005"),
            output_price_per_1k_usd=Decimal("0.015"),
        )

        await uc.execute("m-1", req, request_id="req-1")

        updated_model = repo.update.call_args[0][0]
        assert updated_model.pricing_updated_at is not None
        assert updated_model.pricing_updated_at >= old_ts


class TestInvalidationGuard:
    """★ M1 G1 핵심 회귀 가드 — invalidate 호출 검증."""

    @pytest.mark.asyncio
    async def test_calls_cost_calculator_invalidate_with_model_id(self):
        model = _make_model("m-target")
        uc, _, cost_calc, _ = _make_use_case(model)
        req = UpdatePricingRequest(
            input_price_per_1k_usd=Decimal("0.005"),
            output_price_per_1k_usd=Decimal("0.015"),
        )

        await uc.execute("m-target", req, request_id="req-1")

        cost_calc.invalidate.assert_called_once_with("m-target")

    @pytest.mark.asyncio
    async def test_invalidate_called_after_repo_update(self):
        """update 성공 후에만 invalidate (실패 시 caching이 깨지지 않게)."""
        model = _make_model()
        uc, repo, cost_calc, _ = _make_use_case(model)
        # update 실패 시 invalidate 호출되지 않아야 함
        repo.update = AsyncMock(side_effect=RuntimeError("DB down"))
        req = UpdatePricingRequest(
            input_price_per_1k_usd=Decimal("0.005"),
            output_price_per_1k_usd=Decimal("0.015"),
        )

        with pytest.raises(RuntimeError):
            await uc.execute("m-1", req, request_id="req-1")

        cost_calc.invalidate.assert_not_called()


class TestNotFound:
    @pytest.mark.asyncio
    async def test_raises_value_error_when_model_not_found(self):
        uc, _, cost_calc, _ = _make_use_case(None)
        req = UpdatePricingRequest(
            input_price_per_1k_usd=Decimal("0.005"),
            output_price_per_1k_usd=Decimal("0.015"),
        )

        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute("m-ghost", req, request_id="req-1")

        cost_calc.invalidate.assert_not_called()
