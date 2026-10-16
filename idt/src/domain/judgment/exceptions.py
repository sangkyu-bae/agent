"""judgment 예외 계층.

Design Ref: judgment-backend §3.2 — 포트 밖으로는 `JudgmentError` 계열만 나간다.
소비 지점은 `JudgmentError` 하나만 잡는다(D10).
메시지에 API 키·state 원문을 넣지 않는다.
"""

from __future__ import annotations

from src.domain.judgment.value_objects import JudgmentBackendKind


class JudgmentError(Exception):
    """판정 백엔드 호출 실패의 공통 조상."""

    def __init__(self, backend: JudgmentBackendKind, message: str) -> None:
        super().__init__(f"{backend.value}: {message}")
        self.backend = backend


class JudgmentTimeoutError(JudgmentError):
    """`judgment_timeout_seconds` 초과."""

    def __init__(self, backend: JudgmentBackendKind, timeout_seconds: float) -> None:
        super().__init__(backend, f"timed out after {timeout_seconds:.1f}s")
        self.timeout_seconds = timeout_seconds


class JudgmentUnavailableError(JudgmentError):
    """연결 실패·4xx/5xx·서버 다운 — 지금은 이 백엔드를 쓸 수 없다."""

    def __init__(
        self,
        backend: JudgmentBackendKind,
        message: str,
        status: int | None = None,
    ) -> None:
        suffix = f" (status={status})" if status is not None else ""
        super().__init__(backend, f"{message}{suffix}")
        self.status = status


class JudgmentProtocolError(JudgmentError):
    """응답은 받았지만 스키마·확률이 계약을 어겼다."""

    def __init__(self, backend: JudgmentBackendKind, detail: str) -> None:
        super().__init__(backend, f"protocol violation: {detail}")
        self.detail = detail
