"""EvalPolicy — 답변 평가 검증·집계 순수 규칙 (agent-eval-gate Design §3-2)."""


class EvalPolicy:
    COMMENT_MAX = 500

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
