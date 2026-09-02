"""스윕 소유권 은닉 검증.

Design Ref: §7 — 미소유 스윕은 403이 아니라 404로 은닉한다.
403은 "그 id는 존재한다"는 정보를 흘리기 때문이다 (eval_router 선례).
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.eval_sweep.use_cases import (
    DeleteSweepUseCase,
    GetSweepDetailUseCase,
)
from src.domain.eval_sweep.entity import EvaluationSweep

OWNER = "u-owner"
OTHER = "u-other"


def _sweep(user_id=OWNER):
    return EvaluationSweep(
        id="sw-1",
        name="스윕",
        agent_id="ag-1",
        testset_id="ts-1",
        judge_llm_model_id="m-judge",
        model_ids=["m-1"],
        metrics=["answer_relevancy"],
        total_runs=1,
        user_id=user_id,
        created_at=datetime.now(timezone.utc),
    )


def _repo(sweep):
    repo = MagicMock()
    repo.get = AsyncMock(return_value=sweep)
    repo.get_rows = AsyncMock(return_value=[])
    repo.delete = AsyncMock(return_value=True)
    return repo


def _detail_uc(sweep):
    repo = _repo(sweep)
    llm_repo = MagicMock()
    llm_repo.find_by_id = AsyncMock(return_value=None)
    return GetSweepDetailUseCase(repo, llm_repo, MagicMock()), repo


class TestDetailVisibility:
    @pytest.mark.asyncio
    async def test_owner_can_read(self):
        uc, _ = _detail_uc(_sweep())

        detail = await uc.execute("sw-1", "req-1", scope_user_id=OWNER)

        assert detail.id == "sw-1"

    @pytest.mark.asyncio
    async def test_admin_scope_none_can_read_any(self):
        """_scope(admin)=None — 전체 열람."""
        uc, _ = _detail_uc(_sweep())

        detail = await uc.execute("sw-1", "req-1", scope_user_id=None)

        assert detail.id == "sw-1"

    @pytest.mark.asyncio
    async def test_other_user_is_denied_as_not_found(self):
        uc, _ = _detail_uc(_sweep())

        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute("sw-1", "req-1", scope_user_id=OTHER)

    @pytest.mark.asyncio
    async def test_missing_sweep_is_not_found(self):
        uc, _ = _detail_uc(None)

        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute("sw-1", "req-1", scope_user_id=OWNER)


class TestDeleteVisibility:
    @pytest.mark.asyncio
    async def test_owner_can_delete(self):
        repo = _repo(_sweep())
        uc = DeleteSweepUseCase(repo, MagicMock())

        await uc.execute("sw-1", "req-1", scope_user_id=OWNER)

        repo.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_other_user_cannot_delete(self):
        repo = _repo(_sweep())
        uc = DeleteSweepUseCase(repo, MagicMock())

        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute("sw-1", "req-1", scope_user_id=OTHER)

        repo.delete.assert_not_awaited()
