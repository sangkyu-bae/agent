"""validate_gated_workers 단위 테스트 — 생성·수정 경로 공용 (Check G10)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_builder.gated_worker_validation import (
    validate_gated_workers,
)
from src.domain.agent_builder.schemas import WorkerDefinition


def _w(tool_id, worker_id="w1"):
    return WorkerDefinition(tool_id=tool_id, worker_id=worker_id, description="")


def _repo(entries=None, raises=False):
    repo = MagicMock()
    repo.list_active = AsyncMock(
        side_effect=RuntimeError("down") if raises else None,
        return_value=entries or [],
    )
    return repo


def _entry(tool_id, requires_approval):
    return MagicMock(tool_id=tool_id, requires_approval=requires_approval)


class TestValidateGatedWorkers:
    @pytest.mark.asyncio
    async def test_게이트_도구를_다른_도구와_묶으면_거부(self):
        repo = _repo([_entry("internal:email_send", True)])
        with pytest.raises(ValueError):
            await validate_gated_workers(
                repo, [_w("tavily_search"), _w("email_send")], "r", MagicMock()
            )

    @pytest.mark.asyncio
    async def test_단독이면_통과(self):
        repo = _repo([_entry("internal:email_send", True)])
        await validate_gated_workers(
            repo, [_w("tavily_search", "w1"), _w("email_send", "w2")], "r", MagicMock()
        )

    @pytest.mark.asyncio
    async def test_internal_접두사를_벗긴_저장형식도_매칭한다(self):
        """카탈로그 internal:{id} ↔ agent_tool {id} 표기 차이."""
        repo = _repo([_entry("internal:email_send", True)])
        with pytest.raises(ValueError):
            await validate_gated_workers(
                repo, [_w("x"), _w("email_send")], "r", MagicMock()
            )

    @pytest.mark.asyncio
    async def test_카탈로그_미주입이면_건너뛴다(self):
        await validate_gated_workers(
            None, [_w("a"), _w("b")], "r", MagicMock()
        )

    @pytest.mark.asyncio
    async def test_카탈로그_장애면_경고_후_건너뛴다(self):
        logger = MagicMock()
        await validate_gated_workers(
            _repo(raises=True), [_w("a"), _w("b")], "r", logger
        )
        assert logger.warning.called
