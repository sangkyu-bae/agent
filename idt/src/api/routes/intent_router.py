"""의도 분석 엔드포인트 — POST /api/v1/intent/analyze.

Design Ref: §4.1~§4.2.
- 분류 체계(labels)를 요청 본문으로 받으므로, 이 API 는 특정 도메인에 묶이지 않는다.
- **LLM 실패는 5xx 가 아니라 200 + degraded=true** 로 응답한다. 호출자가 에러
  핸들링 없이 '의도 모름 = 기존대로'로 진행할 수 있어야 하기 때문이다 (Plan D6).
- try/except 를 두지 않는다 — 어댑터가 모든 실패를 흡수하는 것이 계약이다.

DI placeholder 는 main.py 에서 override 한다.
"""
from fastapi import APIRouter, Depends

from src.application.intent.use_case import AnalyzeIntentUseCase
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user
from src.interfaces.schemas.intent import AnalyzeIntentRequest, AnalyzeIntentResponse

router = APIRouter(prefix="/api/v1/intent", tags=["intent"])


def get_analyze_intent_use_case() -> AnalyzeIntentUseCase:
    raise NotImplementedError("AnalyzeIntentUseCase not initialized")


@router.post("/analyze", response_model=AnalyzeIntentResponse)
async def analyze_intent(
    request: AnalyzeIntentRequest,
    current_user: User = Depends(get_current_user),
    use_case: AnalyzeIntentUseCase = Depends(get_analyze_intent_use_case),
) -> AnalyzeIntentResponse:
    """메시지의 의도를 판정한다.

    Returns:
        200: 판정 결과. degraded=true 면 판정 실패(= 의도 모름)이며 에러가 아니다.

    Errors:
        401: 인증 실패 (get_current_user)
        422: labels 2개 미만 / description 누락 / message 빈 문자열
    """
    result = await use_case.execute(
        message=request.message,
        spec=request.spec,
        history=request.history,
        request_id=str(current_user.id),
    )
    return AnalyzeIntentResponse(**result.model_dump())
