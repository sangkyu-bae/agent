"""GetNegativeDrilldownUseCase 테스트 (negative-feedback-drilldown Design §4.5, §8.3)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.application.agent_run.use_cases.get_message_retrievals_use_case import (
    MessageRetrievalsDto,
)
from src.application.eval.drilldown_use_case import (
    GetNegativeDrilldownUseCase,
    NegativeDrilldownDto,
)
from src.domain.conversation.value_objects import MessageRole

ANSWER_ID = 284
QUESTION_ID = 283
ADMIN_ID = "1"
QUESTION_TEXT = "질문 원문"
ANSWER_TEXT = "답변 원문"


def _msg(msg_id, role, turn, content="", agent_id="a1"):
    msg = MagicMock()
    msg.id = MagicMock(value=msg_id)
    msg.role = role
    msg.turn_index = MagicMock(value=turn)
    msg.content = content
    msg.agent_id = MagicMock(value=agent_id)
    msg.user_id = MagicMock(value="owner")
    msg.session_id = MagicMock(value="sess")
    return msg


def _answer(turn=4, role=MessageRole.ASSISTANT):
    return _msg(ANSWER_ID, role, turn, ANSWER_TEXT)


def _question(turn=3):
    return _msg(QUESTION_ID, MessageRole.USER, turn, QUESTION_TEXT)


def _make(has_negative=True, message=None, session_msgs=None, runs=None):
    fb_repo = MagicMock()
    fb_repo.has_negative = AsyncMock(return_value=has_negative)
    msg_repo = MagicMock()
    msg_repo.find_by_id = AsyncMock(return_value=message)
    msg_repo.find_by_session = AsyncMock(return_value=session_msgs or [])
    retrievals = MagicMock()
    retrievals.execute = AsyncMock(
        return_value=MessageRetrievalsDto(message_id=QUESTION_ID, runs=runs or [])
    )
    logger = MagicMock()
    uc = GetNegativeDrilldownUseCase(fb_repo, msg_repo, retrievals, logger)
    return uc, fb_repo, msg_repo, retrievals, logger


class TestNotFound:
    async def test_down_평가가_없으면_메시지를_읽지_않고_거부(self):
        uc, _, msg_repo, retrievals, _ = _make(has_negative=False, message=_answer())

        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute(ANSWER_ID, ADMIN_ID, "r")

        msg_repo.find_by_id.assert_not_awaited()
        retrievals.execute.assert_not_awaited()

    async def test_원본_메시지가_삭제되면_거부(self):
        uc, *_ = _make(message=None)

        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute(ANSWER_ID, ADMIN_ID, "r")

    async def test_user_메시지에_달린_down은_거부(self):
        uc, *_ = _make(message=_answer(role=MessageRole.USER))

        with pytest.raises(ValueError, match="찾을 수 없"):
            await uc.execute(ANSWER_ID, ADMIN_ID, "r")


class TestQuestionRestore:
    async def test_런은_assistant_id가_아니라_질문_id로_조회한다(self):
        """Plan RISK: assistant id로 조회하면 200 빈 runs로 조용히 실패한다."""
        answer = _answer(turn=4)
        uc, _, _, retrievals, _ = _make(
            message=answer, session_msgs=[_question(turn=3), answer]
        )

        await uc.execute(ANSWER_ID, ADMIN_ID, "r")

        retrievals.execute.assert_awaited_once_with(
            message_id=QUESTION_ID, requesting_user_id=ADMIN_ID, is_admin=True,
        )

    async def test_세션_조회는_세션_소유자_기준이다(self):
        answer = _answer()
        uc, _, msg_repo, _, _ = _make(message=answer, session_msgs=[answer])

        await uc.execute(ANSWER_ID, ADMIN_ID, "r")

        msg_repo.find_by_session.assert_awaited_once_with(
            answer.user_id, answer.session_id
        )

    async def test_같은_turn_과거_행도_복원한다(self):
        answer = _answer(turn=13)
        uc, _, _, retrievals, _ = _make(
            message=answer, session_msgs=[_question(turn=13), answer]
        )

        dto = await uc.execute(ANSWER_ID, ADMIN_ID, "r")

        assert dto.question == QUESTION_TEXT
        assert retrievals.execute.await_args.kwargs["message_id"] == QUESTION_ID

    async def test_복원_실패는_답변만_돌려주고_런을_조회하지_않는다(self):
        answer = _answer()
        uc, _, _, retrievals, _ = _make(message=answer, session_msgs=[answer])

        dto = await uc.execute(ANSWER_ID, ADMIN_ID, "r")

        assert dto.question is None
        assert dto.answer == ANSWER_TEXT
        assert dto.runs == []
        retrievals.execute.assert_not_awaited()


class TestResult:
    async def test_질문_답변_런을_조합한다(self):
        answer = _answer()
        run_node = MagicMock()
        uc, *_ = _make(
            message=answer, session_msgs=[_question(), answer], runs=[run_node]
        )

        dto = await uc.execute(ANSWER_ID, ADMIN_ID, "r")

        assert dto == NegativeDrilldownDto(
            message_id=ANSWER_ID, agent_id="a1", question=QUESTION_TEXT,
            answer=ANSWER_TEXT, runs=[run_node],
        )


class TestAccessLog:
    async def test_조회자와_메시지를_기록하고_본문은_남기지_않는다(self):
        answer = _answer()
        uc, _, _, _, logger = _make(message=answer, session_msgs=[_question(), answer])

        await uc.execute(ANSWER_ID, ADMIN_ID, "req-1")

        logger.info.assert_called_once()
        call = logger.info.call_args
        assert call.kwargs["admin_id"] == ADMIN_ID
        assert call.kwargs["message_id"] == ANSWER_ID
        assert call.kwargs["request_id"] == "req-1"
        logged = str(call)
        assert QUESTION_TEXT not in logged
        assert ANSWER_TEXT not in logged

    async def test_거부된_조회는_성공_로그를_남기지_않는다(self):
        uc, _, _, _, logger = _make(has_negative=False)

        with pytest.raises(ValueError):
            await uc.execute(ANSWER_ID, ADMIN_ID, "r")

        logger.info.assert_not_called()
