"""background-jobs 애플리케이션 예외."""


class JobNotFoundError(Exception):
    """미존재·타인 소유·비가시 에이전트 → 404 (사유 비구분)."""


class JobConflictError(Exception):
    """같은 세션에 진행중 job 존재 → 409 (D5)."""
