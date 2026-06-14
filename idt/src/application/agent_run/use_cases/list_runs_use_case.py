"""ListRunsUseCase: 어드민 Run list/페이지네이션 (M5).

agent-run-observability-m5 Design §3.3.

핵심:
- `asyncio.gather`로 list_runs + count_runs 동시 실행 (같은 filters)
- validation 캡슐화 — status enum / limit cap / from <= to
"""
import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from src.domain.agent_run.entities import AgentRun
from src.domain.agent_run.interfaces import (
    AgentRunRepositoryInterface,
    RunListFilters,
)
from src.domain.agent_run.value_objects import RunStatus
from src.domain.logging.interfaces.logger_interface import LoggerInterface


_MAX_LIMIT = 100
_VALID_STATUSES = {s.value for s in RunStatus}


@dataclass(frozen=True)
class RunListDto:
    rows: List[AgentRun]
    total: int
    from_dt: Optional[datetime]
    to_dt: Optional[datetime]
    limit: int
    offset: int


class ListRunsUseCase:
    def __init__(
        self,
        agent_run_repo: AgentRunRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._agent_run_repo = agent_run_repo
        self._logger = logger

    async def execute(self, filters: RunListFilters) -> RunListDto:
        self._validate(filters)
        rows, total = await asyncio.gather(
            self._agent_run_repo.list_runs(filters),
            self._agent_run_repo.count_runs(filters),
        )
        return RunListDto(
            rows=rows,
            total=total,
            from_dt=filters.from_dt,
            to_dt=filters.to_dt,
            limit=filters.limit,
            offset=filters.offset,
        )

    def _validate(self, filters: RunListFilters) -> None:
        if filters.limit < 1 or filters.limit > _MAX_LIMIT:
            raise ValueError(
                f"limit must be between 1 and {_MAX_LIMIT} (got {filters.limit})"
            )
        if filters.offset < 0:
            raise ValueError("offset must be >= 0")
        if filters.status is not None and filters.status not in _VALID_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(_VALID_STATUSES)}"
            )
        if (
            filters.from_dt is not None
            and filters.to_dt is not None
            and filters.from_dt > filters.to_dt
        ):
            raise ValueError("from must be <= to")
