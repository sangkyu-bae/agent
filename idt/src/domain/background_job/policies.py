"""background-jobs 도메인 정책 (Design §4-1).

- JobTransitionPolicy: 상태 전이 허용 매트릭스 (D2·D6·D7)
- JobQueuePolicy: 에러 메시지 절단·동시 상한 검증 (D8)
"""

ERROR_MESSAGE_MAX = 2000

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "failed"}),
    "running": frozenset({"success", "failed"}),
}


class JobTransitionPolicy:
    """상태 전이 규칙 — 종결 상태(success/failed)에서의 재전이는 불허."""

    @staticmethod
    def can_transition(current: str, new: str) -> bool:
        return new in _ALLOWED_TRANSITIONS.get(current, frozenset())


class JobQueuePolicy:
    @staticmethod
    def truncate_error(message: str | None) -> str | None:
        if message is None:
            return None
        return message[:ERROR_MESSAGE_MAX]

    @staticmethod
    def validate_concurrency(limit: int) -> None:
        if limit < 1:
            raise ValueError(f"동시 실행 상한은 1 이상이어야 합니다: {limit}")
