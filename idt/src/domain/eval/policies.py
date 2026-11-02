"""EvalPolicy — 답변 평가 검증·집계 순수 규칙 (agent-eval-gate Design §3-2)."""
from src.domain.conversation.entities import ConversationMessage
from src.domain.conversation.value_objects import MessageRole


class EvalPolicy:
    COMMENT_MAX = 500

    @staticmethod
    def find_question(
        messages: list[ConversationMessage], assistant: ConversationMessage,
    ) -> ConversationMessage | None:
        """👎 답변의 질문(user 메시지) 복원 규칙.

        Design Ref: agent-run-turn-index-fix §6.2 D6 (Plan FR-05/FR-06).
        1차: turn-1 의 USER (정상 저장). 2차: 같은 turn 의 USER — 에이전트 경로
        기존 결함으로 user/assistant 가 같은 turn 으로 저장된 과거 행 호환.
        각 단계에서 정확히 1건일 때만 채택: 0건이면 다음 단계, 2건 이상이면
        모호 → None (평가 저장은 유지, 환류만 건너뛴다).
        """
        target = assistant.turn_index.value
        for turn in (target - 1, target):
            hits = [
                m for m in messages
                if m.turn_index.value == turn and m.role == MessageRole.USER
            ]
            if len(hits) == 1:
                return hits[0]
            if len(hits) > 1:
                return None
        return None

    @staticmethod
    def validate_comment(comment: str | None) -> None:
        """코멘트가 COMMENT_MAX를 초과하면 ValueError (None·빈 값 허용)."""
        if comment is not None and len(comment) > EvalPolicy.COMMENT_MAX:
            raise ValueError(
                f"코멘트는 {EvalPolicy.COMMENT_MAX}자를 초과할 수 없습니다."
            )

    @staticmethod
    def satisfaction(up: int, down: int) -> float | None:
        """만족도 = up / (up + down). 평가 0건이면 None (0 나눗셈 방지)."""
        total = up + down
        if total == 0:
            return None
        return up / total
