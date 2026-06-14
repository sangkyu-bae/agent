"""M5: GetMyUsageTimeseriesUseCase — user_id 강제 주입."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_run.use_cases.get_my_usage_timeseries_use_case import (
    GetMyUsageTimeseriesUseCase,
)


FROM = datetime(2026, 5, 1, tzinfo=timezone.utc)
TO = datetime(2026, 5, 31, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_forces_user_id_into_aggregator_call() -> None:
    agg = MagicMock()
    agg.timeseries = AsyncMock(return_value=[])
    uc = GetMyUsageTimeseriesUseCase(aggregator=agg)

    await uc.execute("user-99", FROM, TO)

    agg.timeseries.assert_awaited_once_with(FROM, TO, user_id="user-99")
