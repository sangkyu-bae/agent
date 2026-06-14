"""UsageAggregator: 사용자별/LLM별/사용자×LLM 기간별 집계 파사드.

AGENT-OBS-001 §3-4 / M5 dashboard 확장.
"""
from datetime import datetime
from typing import List, Optional

from src.domain.agent_run.interfaces import (
    LlmCallRepositoryInterface,
    LlmUsageRow,
    NodeUsageRow,
    UsageSummaryRow,
    UsageTimeseriesPoint,
    UserUsageRow,
)


class UsageAggregator:
    """Repository 위 얇은 파사드. 단위 변환·집계 로직 추가 시 확장."""

    def __init__(self, llm_call_repo: LlmCallRepositoryInterface) -> None:
        self._repo = llm_call_repo

    async def by_user(
        self, from_dt: datetime, to_dt: datetime
    ) -> List[UserUsageRow]:
        return await self._repo.aggregate_by_user(from_dt, to_dt)

    async def by_llm_model(
        self, from_dt: datetime, to_dt: datetime
    ) -> List[LlmUsageRow]:
        return await self._repo.aggregate_by_llm_model(from_dt, to_dt)

    async def for_user(
        self, user_id: str, from_dt: datetime, to_dt: datetime
    ) -> List[LlmUsageRow]:
        return await self._repo.aggregate_user_x_llm(user_id, from_dt, to_dt)

    async def by_node(
        self, from_dt: datetime, to_dt: datetime
    ) -> List[NodeUsageRow]:
        """M4: 노드별 토큰/비용 GROUP BY (★ M3 step_id JOIN 효과)."""
        return await self._repo.aggregate_by_node(from_dt, to_dt)

    async def summary(
        self,
        from_dt: datetime,
        to_dt: datetime,
        user_id: Optional[str] = None,
    ) -> UsageSummaryRow:
        """M5: 대시보드 카드 4종 단일 응답 — admin/me 공용 (user_id 옵션)."""
        return await self._repo.aggregate_summary(from_dt, to_dt, user_id=user_id)

    async def timeseries(
        self,
        from_dt: datetime,
        to_dt: datetime,
        user_id: Optional[str] = None,
    ) -> List[UsageTimeseriesPoint]:
        """M5: 일자별 시계열 — admin/me 공용."""
        return await self._repo.aggregate_timeseries(from_dt, to_dt, user_id=user_id)
