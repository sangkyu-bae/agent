"""background-jobs 도메인 정책 (Design §4-1).

- JobTransitionPolicy: 상태 전이 허용 매트릭스 (D2·D6·D7)
- JobQueuePolicy: 에러 메시지 절단·동시 상한 검증 (D8)
- JobDeletionPolicy: 소프트 삭제 가능 상태 (jobs-page-revamp §4.2)
"""

ERROR_MESSAGE_MAX = 2000

# jobs-page-revamp: 삭제·정리 대상이 되는 종결 상태
FINISHED_STATUSES = frozenset({"success", "failed"})

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


class JobDeletionPolicy:
    """소프트 삭제 가능 여부 (FR-04).

    진행 중(queued/running) 작업은 워커가 소유한 상태다. 사용자가 지우면
    워커가 종결을 기록할 대상을 잃고 고아 상태가 남는다 — 삭제를 막는다.
    """

    @staticmethod
    def can_delete(status: str) -> bool:
        return status in FINISHED_STATUSES
