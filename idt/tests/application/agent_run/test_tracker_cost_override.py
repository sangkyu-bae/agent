"""RunTracker.record_llm_call cost_usd_override — image-generation-tool D-04."""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.agent_run.tracker import RunTracker
from src.domain.agent_run.value_objects import CostUsd, RunId, RunPurpose, TokenUsage


def _tracker() -> RunTracker:
    t = RunTracker.__new__(RunTracker)
    t._resolver = MagicMock()
    t._resolver.resolve = AsyncMock(return_value="img-model")
    t._cost_calc = MagicMock()
    t._cost_calc.get_pricing = AsyncMock(return_value=(None, None))
    t._logger = MagicMock()
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.begin = MagicMock(return_value=session)
    t._session_factory = MagicMock(return_value=session)
    return t


@pytest.mark.asyncio
async def test_override_sets_cost_without_token_pricing() -> None:
    t = _tracker()
    saved = {}

    class FakeRepo:
        def __init__(self, session): ...
        async def save(self, call): saved["call"] = call

    with patch("src.application.agent_run.tracker.SqlAlchemyLlmCallRepository", FakeRepo):
        await t.record_llm_call(
            run_id=RunId("12345678-1234-1234-1234-123456789abc"), step_id="s", tool_call_id=None, user_id="u", agent_id="a",
            provider="openai", model_name="gpt-image-1", purpose=RunPurpose.IMAGE_GENERATION,
            token_usage=TokenUsage(), latency_ms=1200, status="success",
            cost_usd_override=CostUsd(total_usd=Decimal("0.04")),
        )
    call = saved["call"]
    assert call.cost_usd.total_usd == Decimal("0.04")
    assert call.purpose == RunPurpose.IMAGE_GENERATION
    assert call.token_usage.total_tokens == 0
    t._cost_calc.get_pricing.assert_not_awaited()


def test_image_generation_purpose_exists() -> None:
    assert RunPurpose.IMAGE_GENERATION.value == "image_generation"
