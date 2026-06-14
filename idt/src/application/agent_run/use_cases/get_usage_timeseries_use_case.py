"""GetUsageTimeseriesUseCase (M5 — 일자별 시계열).

admin 전용 (user_id=None 으로 호출). me 컨텍스트는 GetMyUsageTimeseriesUseCase.
"""
from datetime import datetime
from typing import List, Optional

from src.application.agent_run.aggregator import UsageAggregator
from src.domain.agent_run.interfaces import UsageTimeseriesPoint


class GetUsageTimeseriesUseCase:
    def __init__(self, aggregator: UsageAggregator) -> None:
        self._aggregator = aggregator

    async def execute(
        self,
        from_dt: datetime,
        to_dt: datetime,
        user_id: Optional[str] = None,
    ) -> List[UsageTimeseriesPoint]:
        return await self._aggregator.timeseries(from_dt, to_dt, user_id=user_id)
