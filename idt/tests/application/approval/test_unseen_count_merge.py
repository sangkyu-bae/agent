"""벨 배지 합산 단위 테스트 (approval-gate Design §5.5).

`count` 의 의미(총 미확인)를 유지하면서 분해 필드를 추가한 계약을 고정한다.
기존 소비자(AppSidebar 등)가 count 만 읽어도 깨지지 않아야 한다.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.background_job.query_use_cases import CountUnseenUseCase


def _uc(*, jobs=0, approvals=None, counter_raises=False):
    job_repo = MagicMock()
    job_repo.count_unseen = AsyncMock(return_value=jobs)

    counter = None
    if approvals is not None or counter_raises:
        counter = MagicMock()
        counter.count_unseen = AsyncMock(
            side_effect=RuntimeError("DB 장애") if counter_raises
            else None,
            return_value=approvals,
        )
    logger = MagicMock()
    return CountUnseenUseCase(job_repo, logger, approval_counter=counter), logger


class TestMerge:
    @pytest.mark.asyncio
    async def test_총합과_분해를_함께_준다(self):
        uc, _ = _uc(jobs=2, approvals=3)
        r = await uc.execute("u1", "req1")
        assert (r.count, r.jobs, r.approvals) == (5, 2, 3)

    @pytest.mark.asyncio
    async def test_count는_총합이다(self):
        """기존 소비자가 count 만 읽어도 의미가 유지된다."""
        uc, _ = _uc(jobs=7, approvals=1)
        assert (await uc.execute("u1", "req1")).count == 8

    @pytest.mark.asyncio
    async def test_둘_다_0이면_0(self):
        uc, _ = _uc(jobs=0, approvals=0)
        r = await uc.execute("u1", "req1")
        assert (r.count, r.jobs, r.approvals) == (0, 0, 0)


class TestBackwardCompat:
    @pytest.mark.asyncio
    async def test_카운터_미주입이면_기존_동작(self):
        """approval_counter 없이도 예전과 같은 값이 나온다 (무회귀)."""
        uc, _ = _uc(jobs=4)
        r = await uc.execute("u1", "req1")
        assert (r.count, r.jobs, r.approvals) == (4, 4, 0)

    @pytest.mark.asyncio
    async def test_승인_집계_실패는_0으로_낮춘다(self):
        """승인 조회 장애가 벨 배지 전체를 죽이면 안 된다."""
        uc, logger = _uc(jobs=2, counter_raises=True)
        r = await uc.execute("u1", "req1")
        assert (r.count, r.jobs, r.approvals) == (2, 2, 0)
        assert logger.warning.called
