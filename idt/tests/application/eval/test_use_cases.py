"""Eval UseCases 테스트 (agent-eval-gate Design §3-3)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.eval.use_cases import (
    AgentEvalStatsUseCase,
    SubmitFeedbackUseCase,
)
from src.domain.eval.entity import MessageFeedback, Rating


def _message(agent_id="a1"):
    msg = MagicMock()
    msg.agent_id = MagicMock(value=agent_id)
    return msg


def _existing(rating=Rating.UP):
    return MessageFeedback(
        id=1, message_id=1, user_id="u1", agent_id="a1", rating=rating,
    )


def _make_submit(message=None, existing=None):
    fb_repo = MagicMock()
    fb_repo.find_by_message_and_user = AsyncMock(return_value=existing)
    fb_repo.upsert = AsyncMock(side_effect=lambda f, request_id: f)
    fb_repo.delete = AsyncMock(return_value=True)
    msg_repo = MagicMock()
    msg_repo.find_by_id = AsyncMock(return_value=message)
    uc = SubmitFeedbackUseCase(fb_repo, msg_repo, MagicMock())
    return uc, fb_repo


class TestSubmit:
    async def test_신규_평가_저장_agent_id_파생(self):
        uc, fb_repo = _make_submit(message=_message(agent_id="general-chat"))

        saved = await uc.execute("u1", 1, "up", None, "r")

        assert saved.rating == Rating.UP
        assert saved.agent_id == "general-chat"
        fb_repo.upsert.assert_awaited_once()

    async def test_같은_rating_재요청은_취소(self):
        uc, fb_repo = _make_submit(
            message=_message(), existing=_existing(Rating.UP)
        )

        result = await uc.execute("u1", 1, "up", None, "r")

        assert result is None  # 취소됨
        fb_repo.delete.assert_awaited_once()
        fb_repo.upsert.assert_not_awaited()

    async def test_반대_rating은_갱신(self):
        uc, fb_repo = _make_submit(
            message=_message(), existing=_existing(Rating.UP)
        )

        result = await uc.execute("u1", 1, "down", None, "r")

        assert result.rating == Rating.DOWN
        fb_repo.upsert.assert_awaited_once()
        fb_repo.delete.assert_not_awaited()

    async def test_미존재_메시지는_찾을_수_없음(self):
        uc, _ = _make_submit(message=None)
        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute("u1", 999, "up", None, "r")

    async def test_불량_rating_거부(self):
        uc, _ = _make_submit(message=_message())
        with pytest.raises(ValueError, match="지원하지 않는"):
            await uc.execute("u1", 1, "meh", None, "r")

    async def test_코멘트_초과_거부(self):
        uc, _ = _make_submit(message=_message())
        with pytest.raises(ValueError):
            await uc.execute("u1", 1, "up", "가" * 501, "r")


class TestAgentStats:
    async def test_만족도_계산(self):
        fb_repo = MagicMock()
        fb_repo.aggregate_by_agent = AsyncMock(
            return_value=[("a1", 8, 2), ("a2", 0, 0)]
        )
        fb_repo.recent_negative = AsyncMock(return_value=[])
        uc = AgentEvalStatsUseCase(fb_repo, recent_negative_limit=20)

        stats = {s.agent_id: s for s in await uc.agents("r")}

        assert stats["a1"].satisfaction == 0.8
        assert stats["a2"].satisfaction is None  # 0건
