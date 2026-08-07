"""웹훅 공개 inbound 라우터 — JWT 의존성 없음 (Design §4-4).

인가는 오직 HMAC 서명 검증(InvokeWebhookAgentUseCase)으로 수행한다.
서명은 raw body 바이트 기준이므로 request.body()를 그대로 전달하고,
pydantic 파싱은 검증 통과 후 use case 내부에서 수행한다.

⚠️ 이 라우터에 get_current_user 류 인증 의존성을 추가하지 말 것 —
외부 시스템은 JWT를 쓸 수 없다 (Design §8 리뷰 포인트).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.application.agent_builder.schemas import RunAgentResponse
from src.application.agent_webhook.invoke_webhook_agent_use_case import (
    WebhookAuthError,
    WebhookBadRequestError,
    WebhookNotFoundError,
)
from src.domain.agent_webhook.policies import WebhookSignaturePolicy

router = APIRouter(prefix="/api/v1/webhooks", tags=["Agent Webhook (Public)"])


def get_invoke_webhook_use_case():
    raise NotImplementedError


@router.post("/agents/{agent_id}", response_model=RunAgentResponse)
async def invoke_agent_webhook(
    agent_id: str,
    request: Request,
    use_case=Depends(get_invoke_webhook_use_case),
):
    """외부 시스템의 에이전트 동기 실행 진입점 (서명 검증 → 소유자 신원 실행)."""
    request_id = str(uuid.uuid4())
    raw_body = await request.body()
    timestamp = request.headers.get(WebhookSignaturePolicy.HEADER_TIMESTAMP)
    signature = request.headers.get(WebhookSignaturePolicy.HEADER_SIGNATURE)
    try:
        return await use_case.execute(
            agent_id, raw_body, timestamp, signature, request_id
        )
    except WebhookAuthError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="서명 검증 실패",
        )
    except WebhookNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="웹훅을 찾을 수 없습니다",
        )
    except WebhookBadRequestError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="실행 권한 없음")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
