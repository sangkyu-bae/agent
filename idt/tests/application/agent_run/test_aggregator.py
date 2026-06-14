"""UsageAggregator — Repository 위 얇은 파사드 검증."""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_run.aggregator import UsageAggregator
from src.domain.agent_run.interfaces import LlmUsageRow, NodeUsageRow, UserUsageRow


@pytest.mark.asyncio
async def test_by_user_delegates_to_repo() -> None:
    repo = MagicMock()
    rows = [UserUsageRow("u-1", 100, Decimal("0.01"), 5)]
    repo.aggregate_by_user = AsyncMock(return_value=rows)
    agg = UsageAggregator(repo)

    result = await agg.by_user(
        datetime(2026, 5, 1, tzinfo=timezone.utc),
        datetime(2026, 5, 31, tzinfo=timezone.utc),
    )

    assert result == rows
    repo.aggregate_by_user.assert_awaited_once()


@pytest.mark.asyncio
async def test_by_llm_model_delegates_to_repo() -> None:
    repo = MagicMock()
    rows = [LlmUsageRow("m-1", "openai", "gpt-4o", 100, Decimal("0.01"), 1)]
    repo.aggregate_by_llm_model = AsyncMock(return_value=rows)
    agg = UsageAggregator(repo)

    result = await agg.by_llm_model(
        datetime(2026, 5, 1, tzinfo=timezone.utc),
        datetime(2026, 5, 31, tzinfo=timezone.utc),
    )

    assert result == rows


@pytest.mark.asyncio
async def test_for_user_delegates_to_repo() -> None:
    repo = MagicMock()
    rows = [LlmUsageRow("m-1", "openai", "gpt-4o", 100, Decimal("0.01"), 1)]
    repo.aggregate_user_x_llm = AsyncMock(return_value=rows)
    agg = UsageAggregator(repo)

    result = await agg.for_user(
        "u-1",
        datetime(2026, 5, 1, tzinfo=timezone.utc),
        datetime(2026, 5, 31, tzinfo=timezone.utc),
    )

    assert result == rows
    repo.aggregate_user_x_llm.assert_awaited_once_with(
        "u-1",
        datetime(2026, 5, 1, tzinfo=timezone.utc),
        datetime(2026, 5, 31, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_by_node_delegates_to_repo() -> None:
    """M4-4: by_node가 aggregate_by_node에 위임."""
    repo = MagicMock()
    rows = [
        NodeUsageRow("supervisor", 10, 5000, Decimal("0.050")),
        NodeUsageRow("worker_finance", 20, 20000, Decimal("0.300")),
    ]
    repo.aggregate_by_node = AsyncMock(return_value=rows)
    agg = UsageAggregator(repo)

    from_dt = datetime(2026, 5, 1, tzinfo=timezone.utc)
    to_dt = datetime(2026, 5, 31, tzinfo=timezone.utc)
    result = await agg.by_node(from_dt, to_dt)

    assert result == rows
    repo.aggregate_by_node.assert_awaited_once_with(from_dt, to_dt)
