"""AgentRun policies tests — mock 금지 (domain 규칙)."""
from decimal import Decimal

import pytest

from src.domain.agent_run.policies import (
    CostCalculationPolicy,
    RunStatusTransitionPolicy,
)
from src.domain.agent_run.value_objects import CostUsd, RunStatus, TokenUsage


class TestRunStatusTransitionPolicy:
    def test_running_to_success_is_allowed(self) -> None:
        assert RunStatusTransitionPolicy.can_transition(
            RunStatus.RUNNING, RunStatus.SUCCESS
        )

    def test_running_to_failed_is_allowed(self) -> None:
        assert RunStatusTransitionPolicy.can_transition(
            RunStatus.RUNNING, RunStatus.FAILED
        )

    def test_running_to_cancelled_is_allowed(self) -> None:
        assert RunStatusTransitionPolicy.can_transition(
            RunStatus.RUNNING, RunStatus.CANCELLED
        )

    def test_success_to_running_is_rejected(self) -> None:
        assert not RunStatusTransitionPolicy.can_transition(
            RunStatus.SUCCESS, RunStatus.RUNNING
        )

    def test_failed_to_success_is_rejected(self) -> None:
        assert not RunStatusTransitionPolicy.can_transition(
            RunStatus.FAILED, RunStatus.SUCCESS
        )

    def test_terminal_to_terminal_is_rejected(self) -> None:
        assert not RunStatusTransitionPolicy.can_transition(
            RunStatus.SUCCESS, RunStatus.FAILED
        )
        assert not RunStatusTransitionPolicy.can_transition(
            RunStatus.CANCELLED, RunStatus.SUCCESS
        )

    def test_ensure_raises_on_invalid_transition(self) -> None:
        with pytest.raises(ValueError, match="Invalid run status transition"):
            RunStatusTransitionPolicy.ensure(RunStatus.SUCCESS, RunStatus.RUNNING)

    def test_ensure_passes_on_valid_transition(self) -> None:
        RunStatusTransitionPolicy.ensure(RunStatus.RUNNING, RunStatus.SUCCESS)


class TestCostCalculationPolicy:
    def test_none_price_returns_zero_cost(self) -> None:
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=1000, total_tokens=2000)
        cost = CostCalculationPolicy.compute(usage, None, None)
        assert cost == CostUsd()

    def test_only_input_price_none_returns_zero_cost(self) -> None:
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=1000, total_tokens=2000)
        cost = CostCalculationPolicy.compute(usage, None, Decimal("0.015"))
        assert cost == CostUsd()

    def test_only_output_price_none_returns_zero_cost(self) -> None:
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=1000, total_tokens=2000)
        cost = CostCalculationPolicy.compute(usage, Decimal("0.005"), None)
        assert cost == CostUsd()

    def test_zero_tokens_yield_zero_cost(self) -> None:
        usage = TokenUsage()
        cost = CostCalculationPolicy.compute(
            usage, Decimal("0.005"), Decimal("0.015")
        )
        assert cost.input_usd == Decimal("0.000000")
        assert cost.output_usd == Decimal("0.000000")
        assert cost.total_usd == Decimal("0.000000")

    def test_gpt4o_price_calculation(self) -> None:
        # gpt-4o: $5 / 1M input, $15 / 1M output → per 1k: 0.005 / 0.015
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=1000, total_tokens=2000)
        cost = CostCalculationPolicy.compute(
            usage, Decimal("0.005"), Decimal("0.015")
        )
        assert cost.input_usd == Decimal("0.005000")
        assert cost.output_usd == Decimal("0.015000")
        assert cost.total_usd == Decimal("0.020000")

    def test_partial_token_amount(self) -> None:
        usage = TokenUsage(prompt_tokens=500, completion_tokens=250, total_tokens=750)
        cost = CostCalculationPolicy.compute(
            usage, Decimal("0.005"), Decimal("0.015")
        )
        # 500/1000 * 0.005 = 0.0025
        # 250/1000 * 0.015 = 0.00375
        assert cost.input_usd == Decimal("0.002500")
        assert cost.output_usd == Decimal("0.003750")
        assert cost.total_usd == Decimal("0.006250")

    def test_decimal_precision_is_six_digits(self) -> None:
        usage = TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2)
        cost = CostCalculationPolicy.compute(
            usage, Decimal("0.005"), Decimal("0.015")
        )
        # 1/1000 * 0.005 = 0.000005, 1/1000 * 0.015 = 0.000015
        assert cost.input_usd == Decimal("0.000005")
        assert cost.output_usd == Decimal("0.000015")
        assert cost.total_usd == Decimal("0.000020")
