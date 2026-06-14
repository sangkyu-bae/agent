"""M5: ListMyRunsUseCase — user_id 강제 주입 보안 검증."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_run.use_cases.list_my_runs_use_case import (
    ListMyRunsUseCase,
)
from src.application.agent_run.use_cases.list_runs_use_case import RunListDto
from src.domain.agent_run.interfaces import RunListFilters


def _make_use_case(dto: RunListDto):
    list_runs_uc = MagicMock()
    list_runs_uc.execute = AsyncMock(return_value=dto)
    return ListMyRunsUseCase(list_runs_use_case=list_runs_uc), list_runs_uc


@pytest.mark.asyncio
async def test_forces_user_id_into_filters() -> None:
    """호출자가 다른 user_id 를 시도해도 force_user_id 가 덮어쓴다."""
    dto = RunListDto(rows=[], total=0, from_dt=None, to_dt=None, limit=20, offset=0)
    uc, list_runs_uc = _make_use_case(dto)

    filters = RunListFilters(user_id="attacker-tries-other-user", agent_id="a-1")
    await uc.execute(user_id="legitimate-self", filters=filters)

    forwarded = list_runs_uc.execute.call_args.args[0]
    assert forwarded.user_id == "legitimate-self"
    assert forwarded.agent_id == "a-1"


@pytest.mark.asyncio
async def test_preserves_other_filters() -> None:
    dto = RunListDto(rows=[], total=0, from_dt=None, to_dt=None, limit=10, offset=0)
    uc, list_runs_uc = _make_use_case(dto)

    filters = RunListFilters(
        from_dt=datetime(2026, 5, 1, tzinfo=timezone.utc),
        to_dt=datetime(2026, 5, 31, tzinfo=timezone.utc),
        agent_id="a-1",
        status="SUCCESS",
        limit=10,
        offset=0,
    )
    await uc.execute(user_id="u-1", filters=filters)

    forwarded = list_runs_uc.execute.call_args.args[0]
    assert forwarded.from_dt == filters.from_dt
    assert forwarded.to_dt == filters.to_dt
    assert forwarded.agent_id == "a-1"
    assert forwarded.status == "SUCCESS"
    assert forwarded.limit == 10
    assert forwarded.offset == 0


@pytest.mark.asyncio
async def test_returns_dto_from_list_runs() -> None:
    dto = RunListDto(rows=[], total=7, from_dt=None, to_dt=None, limit=20, offset=0)
    uc, _ = _make_use_case(dto)

    result = await uc.execute(user_id="u-1", filters=RunListFilters())

    assert result is dto
