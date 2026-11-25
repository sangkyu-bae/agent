"""알림 수신 공개 라우터 — JWT 의존성 없음 (firewall-agent design §4.3).

인가는 오직 Bearer 수신 토큰(해시 비교)으로 ReceiveAlertUseCase 안에서 한다.
⚠️ 이 라우터에 get_current_user 류 인증 의존성을 추가하지 말 것 — Grafana·Alertmanager 는
JWT 를 쓸 수 없다 (webhook_public_router 와 같은 규칙).
인증 뒤의 결과(중복·꺼짐·깨진 본문 등)는 모두 202 — 재전송 루프를 만들지 않는다.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.application.agent_alert.receive_alert_use_case import AlertAuthError
from src.application.agent_alert.schemas import ReceiveAlertResponse
from src.config import settings

router = APIRouter(prefix="/api/v1/alert-hooks", tags=["Agent Alert Hook (Public)"])


def get_receive_alert_use_case():
    raise NotImplementedError


@router.post(
    "/agents/{agent_id}",
    response_model=ReceiveAlertResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def receive_alert(
    agent_id: str,
    request: Request,
    use_case=Depends(get_receive_alert_use_case),
):
    """Alertmanager 형식 알림 수신 → 백그라운드 잡 등록 (실행은 워커)."""
    request_id = str(uuid.uuid4())
    raw_body = await request.body()
    if len(raw_body) > settings.alert_hook_max_body_bytes:
        raise HTTPException(
            status_code=413,  # Starlette 상수명이 버전마다 달라 숫자로 둔다
            detail="payload too large",
        )
    try:
        return await use_case.execute(
            agent_id, request.headers.get("Authorization"), raw_body, request_id
        )
    except AlertAuthError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized"
        )
