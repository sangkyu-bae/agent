"""GetUsageByNodeUseCase (M4 — ★ M3 step_id JOIN 효과)."""
from datetime import datetime
from typing import List

from src.application.agent_run.aggregator import UsageAggregator
from src.domain.agent_run.interfaces import NodeUsageRow


class GetUsageByNodeUseCase:
    def __init__(self, aggregator: UsageAggregator) -> None:
        self._aggregator = aggregator

    async def execute(
        self, from_dt: datetime, to_dt: datetime
    ) -> List[NodeUsageRow]:
        return await self._aggregator.by_node(from_dt, to_dt)
