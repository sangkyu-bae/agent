"""의도 분석 도메인 포트.

Design Ref: §2.3 — application 레이어는 이 인터페이스에만 의존하고,
구체 구현(LLM 호출)은 infrastructure 에서 제공한다.

Plan SC: 실패 시 예외를 던지지 않고 degraded=True 결과를 반환해 본 흐름을 막지
않는다 (Plan D6). 구현체는 이 계약을 반드시 지켜야 한다.
"""
from abc import ABC, abstractmethod

from src.domain.intent.schemas import IntentResult, IntentSpec, Turn


class IntentAnalyzerInterface(ABC):
    """메시지 의도 판정 포트.

    분류 체계(spec)를 호출 시점에 받으므로, 구현체는 특정 도메인 라벨에
    묶이지 않는다 (Plan D3).
    """

    @abstractmethod
    async def analyze(
        self,
        message: str,
        spec: IntentSpec,
        history: list[Turn] | None = None,
        request_id: str = "",
    ) -> IntentResult:
        """메시지의 의도를 판정한다.

        Args:
            message: 판정 대상 메시지
            spec: 호출자가 정의한 분류 체계
            history: 이전 대화(선택). 없으면 현재 메시지만으로 판정한다.
            request_id: 로그 상관관계 추적용

        Returns:
            판정 결과. 판정을 시도조차 못 한 경우 degraded=True.
            **예외를 던지지 않는다.**
        """
        raise NotImplementedError
