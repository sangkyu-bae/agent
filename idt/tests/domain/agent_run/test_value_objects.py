"""AgentRun value objects tests — mock 금지 (domain 규칙).

AGENT-OBS-001 §2-1 value_objects.py 검증.
"""
from decimal import Decimal

import pytest

from src.domain.agent_run.value_objects import (
    CostUsd,
    NodeType,
    RunId,
    RunPurpose,
    RunStatus,
    StepStatus,
    TokenUsage,
)


class TestRunId:
    def test_valid_uuid_string_is_accepted(self) -> None:
        run_id = RunId("11111111-2222-3333-4444-555555555555")
        assert run_id.value == "11111111-2222-3333-4444-555555555555"

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="UUID"):
            RunId("")

    def test_too_short_string_raises(self) -> None:
        with pytest.raises(ValueError, match="UUID"):
            RunId("abc")


class TestRunStatus:
    def test_str_enum_values(self) -> None:
        assert RunStatus.RUNNING.value == "RUNNING"
        assert RunStatus.SUCCESS.value == "SUCCESS"
        assert RunStatus.FAILED.value == "FAILED"
        assert RunStatus.CANCELLED.value == "CANCELLED"


class TestStepStatus:
    def test_str_enum_values(self) -> None:
        assert StepStatus.STARTED.value == "STARTED"
        assert StepStatus.SUCCESS.value == "SUCCESS"
        assert StepStatus.FAILED.value == "FAILED"


class TestNodeType:
    def test_str_enum_values(self) -> None:
        assert NodeType.SUPERVISOR.value == "SUPERVISOR"
        assert NodeType.WORKER.value == "WORKER"
        assert NodeType.GATE.value == "GATE"
        assert NodeType.OTHER.value == "OTHER"


class TestRunPurpose:
    def test_str_enum_values(self) -> None:
        assert RunPurpose.SUPERVISOR.value == "supervisor"
        assert RunPurpose.WORKER.value == "worker"
        assert RunPurpose.SUMMARIZER.value == "summarizer"
        assert RunPurpose.QUERY_REWRITE.value == "query_rewrite"
        assert RunPurpose.RERANK.value == "rerank"
        assert RunPurpose.HALLUCINATION_CHECK.value == "hallucination_check"
        assert RunPurpose.OTHER.value == "other"


class TestTokenUsage:
    def test_default_is_zero(self) -> None:
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0

    def test_addition_sums_each_field(self) -> None:
        a = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        b = TokenUsage(prompt_tokens=4, completion_tokens=6, total_tokens=10)
        c = a + b
        assert c == TokenUsage(prompt_tokens=14, completion_tokens=11, total_tokens=25)

    def test_negative_prompt_tokens_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            TokenUsage(prompt_tokens=-1, completion_tokens=0, total_tokens=0)

    def test_negative_completion_tokens_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            TokenUsage(prompt_tokens=0, completion_tokens=-1, total_tokens=0)

    def test_negative_total_tokens_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=-1)


class TestCostUsd:
    def test_default_is_zero(self) -> None:
        cost = CostUsd()
        assert cost.input_usd == Decimal("0")
        assert cost.output_usd == Decimal("0")
        assert cost.total_usd == Decimal("0")

    def test_addition_sums_each_field(self) -> None:
        a = CostUsd(
            input_usd=Decimal("0.001"),
            output_usd=Decimal("0.002"),
            total_usd=Decimal("0.003"),
        )
        b = CostUsd(
            input_usd=Decimal("0.010"),
            output_usd=Decimal("0.020"),
            total_usd=Decimal("0.030"),
        )
        c = a + b
        assert c == CostUsd(
            input_usd=Decimal("0.011"),
            output_usd=Decimal("0.022"),
            total_usd=Decimal("0.033"),
        )

    def test_negative_input_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            CostUsd(
                input_usd=Decimal("-0.01"),
                output_usd=Decimal("0"),
                total_usd=Decimal("0"),
            )

    def test_negative_output_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            CostUsd(
                input_usd=Decimal("0"),
                output_usd=Decimal("-0.01"),
                total_usd=Decimal("0"),
            )

    def test_negative_total_raises(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            CostUsd(
                input_usd=Decimal("0"),
                output_usd=Decimal("0"),
                total_usd=Decimal("-0.01"),
            )
