"""GetUsageMeUseCase (M4): 현재 사용자 본인의 LLM 모델별 사용량."""
from datetime import datetime
from typing import List

from src.application.agent_run.aggregator import UsageAggregator
from src.domain.agent_run.interfaces import LlmUsageRow


class GetUsageMeUseCase:
    def __init__(self, aggregator: UsageAggregator) -> None:
        self._aggregator = aggregator

    async def execute(
        self, user_id: str, from_dt: datetime, to_dt: datetime
    ) -> List[LlmUsageRow]:
        return await self._aggregator.for_user(user_id, from_dt, to_dt)
