"""EvalPolicy.find_question — 👎 답변의 질문 복원 규칙 (agent-run-turn-index-fix Design §6.2 D6).

Plan FR-05: turn-1 USER 우선, 없으면 같은 turn USER(에이전트 경로 과거 중복 행).
Plan FR-06: 어느 단계든 2건 이상이면 모호 → None.
"""
from unittest.mock import MagicMock

from src.domain.conversation.value_objects import MessageRole
from src.domain.eval.policies import EvalPolicy


def _msg(turn: int, role: MessageRole, content: str = "") -> MagicMock:
    m = MagicMock()
    m.turn_index = MagicMock(value=turn)
    m.role = role
    m.content = content or f"{role.value}-{turn}"
    return m


ASSISTANT = _msg(4, MessageRole.ASSISTANT, "답변")


class TestFindQuestion:
    def test_P1_turn_minus_1_user_1건이면_그것(self):
        q = _msg(3, MessageRole.USER, "질문")
        assert EvalPolicy.find_question([q, ASSISTANT], ASSISTANT) is q

    def test_P2_turn_minus_1_없으면_같은_turn_user로_폴백(self):
        """에이전트 경로 기존 결함: user/assistant 가 같은 turn 으로 저장된 과거 행."""
        q = _msg(4, MessageRole.USER, "질문")
        assert EvalPolicy.find_question([q, ASSISTANT], ASSISTANT) is q

    def test_P3_turn_minus_1_user_2건이면_None(self):
        msgs = [_msg(3, MessageRole.USER), _msg(3, MessageRole.USER), ASSISTANT]
        assert EvalPolicy.find_question(msgs, ASSISTANT) is None

    def test_P4_같은_turn_user_2건이면_None(self):
        msgs = [_msg(4, MessageRole.USER), _msg(4, MessageRole.USER), ASSISTANT]
        assert EvalPolicy.find_question(msgs, ASSISTANT) is None

    def test_P5_user_없음이면_None(self):
        msgs = [_msg(3, MessageRole.ASSISTANT), ASSISTANT]
        assert EvalPolicy.find_question(msgs, ASSISTANT) is None

    def test_P6_turn_minus_1에_assistant만_있으면_같은_turn_user(self):
        q = _msg(4, MessageRole.USER, "질문")
        msgs = [_msg(3, MessageRole.ASSISTANT), q, ASSISTANT]
        assert EvalPolicy.find_question(msgs, ASSISTANT) is q

    def test_P7_1차_매칭이_있으면_폴백_후보는_무시(self):
        """신규 행(turn-1)과 같은 turn USER 가 함께 있어도 1차가 이긴다."""
        q3 = _msg(3, MessageRole.USER, "정상 질문")
        q4 = _msg(4, MessageRole.USER, "오염 후보")
        assert EvalPolicy.find_question([q3, q4, ASSISTANT], ASSISTANT) is q3
