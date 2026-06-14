"""GetMyUsageTimeseriesUseCase (M5 — 본인 일자별 시계열).

서버측 user_id 강제 — route 는 current_user.id 를 직접 전달해야 한다.
"""
from datetime import datetime
from typing import List

from src.application.agent_run.aggregator import UsageAggregator
from src.domain.agent_run.interfaces import UsageTimeseriesPoint


class GetMyUsageTimeseriesUseCase:
    def __init__(self, aggregator: UsageAggregator) -> None:
        self._aggregator = aggregator

    async def execute(
        self, user_id: str, from_dt: datetime, to_dt: datetime
    ) -> List[UsageTimeseriesPoint]:
        return await self._aggregator.timeseries(from_dt, to_dt, user_id=user_id)
