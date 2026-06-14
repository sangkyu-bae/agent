"""GetUsageSummaryUseCase (M5 — 대시보드 카드 4종).

admin / me 공용 — user_id 가 주어지면 me 컨텍스트, 없으면 admin 전체.
"""
from datetime import datetime
from typing import Optional

from src.application.agent_run.aggregator import UsageAggregator
from src.domain.agent_run.interfaces import UsageSummaryRow


class GetUsageSummaryUseCase:
    def __init__(self, aggregator: UsageAggregator) -> None:
        self._aggregator = aggregator

    async def execute(
        self,
        from_dt: datetime,
        to_dt: datetime,
        user_id: Optional[str] = None,
    ) -> UsageSummaryRow:
        return await self._aggregator.summary(from_dt, to_dt, user_id=user_id)
