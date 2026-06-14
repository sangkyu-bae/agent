"""M4-6: 4 Usage query use cases — aggregator wrapper 검증."""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_run.use_cases.get_usage_by_llm_use_case import (
    GetUsageByLlmUseCase,
)
from src.application.agent_run.use_cases.get_usage_by_node_use_case import (
    GetUsageByNodeUseCase,
)
from src.application.agent_run.use_cases.get_usage_by_user_use_case import (
    GetUsageByUserUseCase,
)
from src.application.agent_run.use_cases.get_usage_me_use_case import (
    GetUsageMeUseCase,
)
from src.domain.agent_run.interfaces import (
    LlmUsageRow,
    NodeUsageRow,
    UserUsageRow,
)


FROM = datetime(2026, 5, 1, tzinfo=timezone.utc)
TO = datetime(2026, 5, 31, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_get_usage_by_user_delegates_to_aggregator():
    agg = MagicMock()
    rows = [UserUsageRow("u-1", 100, Decimal("0.01"), 5)]
    agg.by_user = AsyncMock(return_value=rows)
    uc = GetUsageByUserUseCase(aggregator=agg)

    result = await uc.execute(FROM, TO)

    assert result == rows
    agg.by_user.assert_awaited_once_with(FROM, TO)


@pytest.mark.asyncio
async def test_get_usage_by_llm_delegates_to_aggregator():
    agg = MagicMock()
    rows = [LlmUsageRow("m-1", "openai", "gpt-4o", 100, Decimal("0.01"), 1)]
    agg.by_llm_model = AsyncMock(return_value=rows)
    uc = GetUsageByLlmUseCase(aggregator=agg)

    result = await uc.execute(FROM, TO)

    assert result == rows
    agg.by_llm_model.assert_awaited_once_with(FROM, TO)


@pytest.mark.asyncio
async def test_get_usage_by_node_delegates_to_aggregator():
    agg = MagicMock()
    rows = [NodeUsageRow("supervisor", 10, 5000, Decimal("0.050"))]
    agg.by_node = AsyncMock(return_value=rows)
    uc = GetUsageByNodeUseCase(aggregator=agg)

    result = await uc.execute(FROM, TO)

    assert result == rows
    agg.by_node.assert_awaited_once_with(FROM, TO)


@pytest.mark.asyncio
async def test_get_usage_me_uses_current_user_id():
    agg = MagicMock()
    rows = [LlmUsageRow("m-1", "openai", "gpt-4o", 100, Decimal("0.01"), 1)]
    agg.for_user = AsyncMock(return_value=rows)
    uc = GetUsageMeUseCase(aggregator=agg)

    result = await uc.execute("user-99", FROM, TO)

    assert result == rows
    agg.for_user.assert_awaited_once_with("user-99", FROM, TO)
