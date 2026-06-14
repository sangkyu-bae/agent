"""M5: GetUsageSummaryUseCase — aggregator.summary 위임 검증."""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_run.use_cases.get_usage_summary_use_case import (
    GetUsageSummaryUseCase,
)
from src.domain.agent_run.interfaces import UsageSummaryRow


FROM = datetime(2026, 5, 1, tzinfo=timezone.utc)
TO = datetime(2026, 5, 31, tzinfo=timezone.utc)


def _sample_row() -> UsageSummaryRow:
    return UsageSummaryRow(
        from_dt=FROM, to_dt=TO,
        total_runs=10, success_runs=9, failed_runs=1,
        total_tokens=1234, total_cost_usd=Decimal("0.123456"),
    )


@pytest.mark.asyncio
async def test_admin_context_passes_user_id_none() -> None:
    agg = MagicMock()
    agg.summary = AsyncMock(return_value=_sample_row())
    uc = GetUsageSummaryUseCase(aggregator=agg)

    result = await uc.execute(FROM, TO)

    agg.summary.assert_awaited_once_with(FROM, TO, user_id=None)
    assert result.total_runs == 10


@pytest.mark.asyncio
async def test_me_context_passes_user_id() -> None:
    agg = MagicMock()
    agg.summary = AsyncMock(return_value=_sample_row())
    uc = GetUsageSummaryUseCase(aggregator=agg)

    await uc.execute(FROM, TO, user_id="user-99")

    agg.summary.assert_awaited_once_with(FROM, TO, user_id="user-99")
