"""판정 백엔드 포트.

Design Ref: judgment-backend §3.3 — 구현(Jev/AnyJev)은 infrastructure/judgment/ 에.
포트는 실패를 `JudgmentError` 계열로 정직하게 던지고 삼키지 않는다(FR-08);
흡수는 "쓸 수 있는 결과"를 아는 소비 지점 어댑터 한 곳이 맡는다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.judgment.value_objects import (
    JudgmentBackendKind,
    JudgmentRequest,
    JudgmentResponse,
)


class JudgmentPort(ABC):
    """state + 질문 묶음 → 확률 답."""

    kind: JudgmentBackendKind

    @abstractmethod
    async def judge(self, request: JudgmentRequest) -> JudgmentResponse:
        """실패 시 JudgmentTimeoutError / JudgmentUnavailableError /
        JudgmentProtocolError.
        """
        raise NotImplementedError

    async def aclose(self) -> None:
        """앱 수명 싱글턴 정리(D15). 기본 no-op."""
        return None
