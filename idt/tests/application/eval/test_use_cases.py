"""Eval UseCases 테스트 (agent-eval-gate Design §3-3 + eval-feedback-loop §3-4)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.eval.use_cases import (
    AgentEvalStatsUseCase,
    SubmitFeedbackUseCase,
)
from src.domain.conversation.value_objects import MessageRole
from src.domain.eval.entity import MessageFeedback, Rating


def _message(agent_id="a1", turn=4, content="답변 내용", role=MessageRole.ASSISTANT):
    msg = MagicMock()
    msg.agent_id = MagicMock(value=agent_id)
    msg.user_id = MagicMock(value="u1")
    msg.session_id = MagicMock()
    msg.turn_index = MagicMock(value=turn)
    msg.role = role
    msg.content = content
    return msg


def _existing(rating=Rating.UP, comment=None):
    return MessageFeedback(
        id=1, message_id=1, user_id="u1", agent_id="a1", rating=rating,
        comment=comment,
    )


def _extraction(feedback_enabled=True):
    ext = MagicMock()
    ext.feedback_enabled = feedback_enabled
    ext.kickoff_feedback = MagicMock()
    return ext


def _make_submit(message=None, existing=None, extraction=None, session_msgs=None):
    fb_repo = MagicMock()
    fb_repo.find_by_message_and_user = AsyncMock(return_value=existing)
    fb_repo.upsert = AsyncMock(side_effect=lambda f, request_id: f)
    fb_repo.delete = AsyncMock(return_value=True)
    msg_repo = MagicMock()
    msg_repo.find_by_id = AsyncMock(return_value=message)
    msg_repo.find_by_session = AsyncMock(return_value=session_msgs or [])
    logger = MagicMock()
    uc = SubmitFeedbackUseCase(fb_repo, msg_repo, logger, extraction=extraction)
    return uc, fb_repo, msg_repo, logger


class TestSubmit:
    async def test_신규_평가_저장_agent_id_파생(self):
        uc, fb_repo, _, _ = _make_submit(message=_message(agent_id="general-chat"))

        saved = await uc.execute("u1", 1, "up", None, "r")

        assert saved.rating == Rating.UP
        assert saved.agent_id == "general-chat"
        fb_repo.upsert.assert_awaited_once()

    async def test_같은_rating_재요청은_취소(self):
        uc, fb_repo, _, _ = _make_submit(
            message=_message(), existing=_existing(Rating.UP)
        )

        result = await uc.execute("u1", 1, "up", None, "r")

        assert result is None  # 취소됨
        fb_repo.delete.assert_awaited_once()
        fb_repo.upsert.assert_not_awaited()

    async def test_반대_rating은_갱신(self):
        uc, fb_repo, _, _ = _make_submit(
            message=_message(), existing=_existing(Rating.UP)
        )

        result = await uc.execute("u1", 1, "down", None, "r")

        assert result.rating == Rating.DOWN
        fb_repo.upsert.assert_awaited_once()
        fb_repo.delete.assert_not_awaited()

    async def test_미존재_메시지는_찾을_수_없음(self):
        uc, _, _, _ = _make_submit(message=None)
        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute("u1", 999, "up", None, "r")

    async def test_불량_rating_거부(self):
        uc, _, _, _ = _make_submit(message=_message())
        with pytest.raises(ValueError, match="지원하지 않는"):
            await uc.execute("u1", 1, "meh", None, "r")

    async def test_코멘트_초과_거부(self):
        uc, _, _, _ = _make_submit(message=_message())
        with pytest.raises(ValueError):
            await uc.execute("u1", 1, "up", "가" * 501, "r")


class TestFeedbackTrigger:
    """eval-feedback-loop §3-4 — comment 있는 down만 추출 트리거 (rev1)."""

    def _qa_setup(self, existing=None, extraction=None, session_msgs=...):
        answer = _message(turn=4, content="답변 내용")
        question = _message(turn=3, content="질문 내용", role=MessageRole.USER)
        if session_msgs is ...:
            session_msgs = [question, answer]
        return _make_submit(
            message=answer, existing=existing,
            extraction=extraction if extraction is not None else _extraction(),
            session_msgs=session_msgs,
        )

    async def test_down_comment_신규는_kickoff_호출(self):
        ext = _extraction()
        uc, _, _, _ = self._qa_setup(extraction=ext)

        await uc.execute("u1", 1, "down", "근거 부족", "r")

        ext.kickoff_feedback.assert_called_once()
        args = ext.kickoff_feedback.call_args.args
        assert args[0] == "u1"          # 대화 소유자
        assert args[1] == "질문 내용"    # 복원된 질문
        assert args[2] == "답변 내용"    # 평가 대상 답변
        assert args[3] == "근거 부족"    # 이유
        assert args[4] == "r"

    async def test_기존_down에_comment_추가도_호출(self):
        ext = _extraction()
        uc, _, _, _ = self._qa_setup(
            existing=_existing(Rating.DOWN, comment=None), extraction=ext
        )

        await uc.execute("u1", 1, "down", "형식 불만", "r")

        ext.kickoff_feedback.assert_called_once()

    async def test_up에서_down_comment_전이도_호출(self):
        ext = _extraction()
        uc, _, _, _ = self._qa_setup(
            existing=_existing(Rating.UP), extraction=ext
        )

        await uc.execute("u1", 1, "down", "질문과 무관", "r")

        ext.kickoff_feedback.assert_called_once()

    async def test_bare_down은_미호출(self):
        ext = _extraction()
        uc, _, msg_repo, _ = self._qa_setup(extraction=ext)

        await uc.execute("u1", 1, "down", None, "r")

        ext.kickoff_feedback.assert_not_called()
        msg_repo.find_by_session.assert_not_awaited()  # Q/A 복원 조회도 없음

    async def test_동일_comment_재제출은_미호출(self):
        ext = _extraction()
        uc, _, _, _ = self._qa_setup(
            existing=_existing(Rating.DOWN, comment="근거 부족"), extraction=ext
        )

        await uc.execute("u1", 1, "down", "근거 부족", "r")

        ext.kickoff_feedback.assert_not_called()

    async def test_down_재클릭_취소는_미호출(self):
        ext = _extraction()
        uc, fb_repo, _, _ = self._qa_setup(
            existing=_existing(Rating.DOWN, comment="근거 부족"), extraction=ext
        )

        result = await uc.execute("u1", 1, "down", None, "r")

        assert result is None  # 취소
        fb_repo.delete.assert_awaited_once()
        ext.kickoff_feedback.assert_not_called()

    async def test_up_comment는_미호출(self):
        ext = _extraction()
        uc, _, _, _ = self._qa_setup(extraction=ext)

        await uc.execute("u1", 1, "up", "좋았어요", "r")

        ext.kickoff_feedback.assert_not_called()

    async def test_extraction_미주입이면_기존_동작(self):
        uc, fb_repo, msg_repo, _ = _make_submit(
            message=_message(), extraction=None
        )

        saved = await uc.execute("u1", 1, "down", "이유", "r")

        assert saved.rating == Rating.DOWN
        msg_repo.find_by_session.assert_not_awaited()

    async def test_feedback_enabled_off면_복원_조회_없이_미호출(self):
        ext = _extraction(feedback_enabled=False)
        uc, _, msg_repo, _ = self._qa_setup(extraction=ext)

        await uc.execute("u1", 1, "down", "이유", "r")

        ext.kickoff_feedback.assert_not_called()
        msg_repo.find_by_session.assert_not_awaited()

    async def test_직전_user_메시지_부재면_warning_후_평가는_성공(self):
        ext = _extraction()
        uc, _, _, logger = self._qa_setup(extraction=ext, session_msgs=[])

        saved = await uc.execute("u1", 1, "down", "이유", "r")

        assert saved.rating == Rating.DOWN  # 평가 저장은 유지 (FR-02)
        ext.kickoff_feedback.assert_not_called()
        logger.warning.assert_called_once()


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
