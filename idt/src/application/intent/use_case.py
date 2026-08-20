"""의도 판정 UseCase.

Design Ref: §2.3 / §9.1 — 라우터와 LangGraph 노드가 공유하는 단일 진입점.
이 계층 덕분에 interfaces 레이어가 domain 포트를 직접 물지 않는다.

의도적으로 얇다:
  - spec 검증 → IntentSpec/SlotSpec 생성 시 pydantic 이 이미 수행 (FR-11/FR-16)
  - 정규화·병합·폴백·로깅 → 어댑터와 Policy 가 이미 수행 (Design E1~E9)
따라서 여기서 하는 일은 위임과 흐름 제어뿐이다.

**try/except 를 두지 않는다** — 포트가 모든 예외를 흡수하는 것이 계약이므로,
계약을 어긴 구현은 조용히 삼키지 않고 드러나야 한다 (Design §6.1).

**Design 이탈**: Design §2.3 은 이 UseCase 가 LoggerInterface 에 의존한다고 했으나,
어댑터가 이미 판정 1회당 구조화 로그 1건을 남기므로 여기서 또 남기면 중복이다.
쓰이지 않는 의존을 두지 않기 위해 logger 를 받지 않는다.
"""
from src.domain.intent.interfaces import IntentAnalyzerInterface
from src.domain.intent.schemas import IntentResult, IntentSpec, SlotAnswer, Turn


class AnalyzeIntentUseCase:
    """메시지 + 분류 체계/축 → 구조화 의도 (+ 미충족 축 되묻기)."""

    def __init__(self, analyzer: IntentAnalyzerInterface) -> None:
        self._analyzer = analyzer

    async def execute(
        self,
        message: str,
        spec: IntentSpec,
        history: list[Turn] | None = None,
        answers: list[SlotAnswer] | None = None,
        round_: int = 0,
        request_id: str = "",
    ) -> IntentResult:
        """의도를 판정한다.

        Args:
            message: 판정 대상 메시지
            spec: 호출자가 정의한 분류 체계 + 물어볼 축
            history: 이전 대화(선택)
            answers: 이전 라운드의 사용자 답변(선택). 왕복은 stateless 이므로
                호출자가 매번 에코백한다 (Plan D4).
            round_: 되묻기 라운드. 상한 clamp 는 Policy 가 수행한다.
            request_id: 로그 상관관계 추적용

        Returns:
            판정 결과. 판정 실패 시 degraded=True (예외가 아니다, Plan D6).
        """
        return await self._analyzer.analyze(
            message=message,
            spec=spec,
            history=history,
            answers=answers,
            round_=round_,
            request_id=request_id,
        )
