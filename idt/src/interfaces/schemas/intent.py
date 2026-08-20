"""의도 분석 API request/response 스키마.

Design Ref: §4.2. 도메인 VO(IntentSpec/Turn/SlotAnswer/IntentResult)를 그대로
재사용해 계약 중복을 만들지 않는다 — 검증 규칙(labels/slots 조건 등)이 한 곳에만
존재한다.
"""
from pydantic import BaseModel, Field

from src.domain.intent.schemas import IntentResult, IntentSpec, SlotAnswer, Turn


class AnalyzeIntentRequest(BaseModel):
    """POST /api/v1/intent/analyze 요청.

    되묻기 왕복은 stateless 다 (Plan D4) — 서버는 라운드 사이에 아무것도 저장하지
    않으므로, 클라이언트가 이전 답변(`answers`)과 라운드(`round`)를 매번 에코백한다.
    """

    message: str = Field(..., min_length=1, description="판정 대상 메시지")
    spec: IntentSpec = Field(..., description="호출자가 정의한 분류 체계 + 물어볼 축")
    history: list[Turn] | None = Field(
        default=None, description="이전 대화(선택). 없으면 현재 메시지만으로 판정"
    )
    answers: list[SlotAnswer] | None = Field(
        default=None,
        description=(
            "이전 라운드에서 사용자가 답한 값(선택). "
            "같은 축에 대해 LLM 추출값보다 우선한다."
        ),
    )
    round: int = Field(
        default=0,
        ge=0,
        description="되묻기 라운드. 서버가 상한으로 clamp 한다.",
    )


class AnalyzeIntentResponse(IntentResult):
    """판정 결과.

    IntentResult 를 그대로 노출한다. degraded=true 는 **에러가 아니라**
    '의도 모름'이며 HTTP 200 으로 응답한다 (Design §4.2).
    """
