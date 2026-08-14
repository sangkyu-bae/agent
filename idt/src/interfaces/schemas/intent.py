"""의도 분석 API request/response 스키마.

Design Ref: §4.2. 도메인 VO(IntentSpec/Turn/IntentResult)를 그대로 재사용해
계약 중복을 만들지 않는다 — 검증 규칙(labels ≥ 2 등)이 한 곳에만 존재한다.
"""
from pydantic import BaseModel, Field

from src.domain.intent.schemas import IntentResult, IntentSpec, Turn


class AnalyzeIntentRequest(BaseModel):
    """POST /api/v1/intent/analyze 요청."""

    message: str = Field(..., min_length=1, description="판정 대상 메시지")
    spec: IntentSpec = Field(..., description="호출자가 정의한 분류 체계")
    history: list[Turn] | None = Field(
        default=None, description="이전 대화(선택). 없으면 현재 메시지만으로 판정"
    )


class AnalyzeIntentResponse(IntentResult):
    """판정 결과.

    IntentResult 를 그대로 노출한다. degraded=true 는 **에러가 아니라**
    '의도 모름'이며 HTTP 200 으로 응답한다 (Design §4.2).
    """
