"""M5: GetUsageTimeseriesUseCase — aggregator.timeseries 위임 검증."""
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_run.use_cases.get_usage_timeseries_use_case import (
    GetUsageTimeseriesUseCase,
)
from src.domain.agent_run.interfaces import UsageTimeseriesPoint


FROM = datetime(2026, 5, 1, tzinfo=timezone.utc)
TO = datetime(2026, 5, 31, tzinfo=timezone.utc)


def _sample_points() -> list[UsageTimeseriesPoint]:
    return [
        UsageTimeseriesPoint(
            bucket=date(2026, 5, 1),
            run_count=3,
            total_tokens=100,
            total_cost_usd=Decimal("0.001"),
        ),
        UsageTimeseriesPoint(
            bucket=date(2026, 5, 2),
            run_count=5,
            total_tokens=300,
            total_cost_usd=Decimal("0.003"),
        ),
    ]


@pytest.mark.asyncio
async def test_admin_context_user_id_none() -> None:
    agg = MagicMock()
    agg.timeseries = AsyncMock(return_value=_sample_points())
    uc = GetUsageTimeseriesUseCase(aggregator=agg)

    points = await uc.execute(FROM, TO)

    agg.timeseries.assert_awaited_once_with(FROM, TO, user_id=None)
    assert len(points) == 2
    assert points[0].bucket == date(2026, 5, 1)


@pytest.mark.asyncio
async def test_me_context_user_id_forwarded() -> None:
    agg = MagicMock()
    agg.timeseries = AsyncMock(return_value=[])
    uc = GetUsageTimeseriesUseCase(aggregator=agg)

    await uc.execute(FROM, TO, user_id="user-7")

    agg.timeseries.assert_awaited_once_with(FROM, TO, user_id="user-7")
