"""ListMyRunsUseCase (M5 — 본인 Run 목록).

서버측에서 user_id 를 강제 주입한다. 호출자(route)가 current_user.id 를 전달해야 한다.
필터에 다른 user_id가 들어오면 force_user_id가 덮어쓴다 — 타사용자 데이터 접근 차단.

검증/페이지네이션/asyncio.gather 로직은 ListRunsUseCase 에 위임한다 (DRY).
"""
from dataclasses import replace

from src.application.agent_run.use_cases.list_runs_use_case import (
    ListRunsUseCase,
    RunListDto,
)
from src.domain.agent_run.interfaces import RunListFilters


class ListMyRunsUseCase:
    def __init__(self, list_runs_use_case: ListRunsUseCase) -> None:
        self._list_runs = list_runs_use_case

    async def execute(
        self, user_id: str, filters: RunListFilters
    ) -> RunListDto:
        forced = replace(filters, user_id=user_id)
        return await self._list_runs.execute(forced)
