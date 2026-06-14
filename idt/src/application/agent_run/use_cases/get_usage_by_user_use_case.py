"""GetUsageByUserUseCase (M4)."""
from datetime import datetime
from typing import List

from src.application.agent_run.aggregator import UsageAggregator
from src.domain.agent_run.interfaces import UserUsageRow


class GetUsageByUserUseCase:
    def __init__(self, aggregator: UsageAggregator) -> None:
        self._aggregator = aggregator

    async def execute(
        self, from_dt: datetime, to_dt: datetime
    ) -> List[UserUsageRow]:
        return await self._aggregator.by_user(from_dt, to_dt)
