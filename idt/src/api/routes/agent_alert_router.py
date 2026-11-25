"""에이전트 알림 수신 설정 라우터 (JWT, 소유자 전용) — firewall-agent design §4.1.

토큰 평문은 최초 생성(PUT)·재발급(POST token) 응답에서만 1회 노출된다.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from src.application.agent_alert.schemas import (
    AlertReceiptResponse,
    AlertReceiverConfigResponse,
    UpsertAlertReceiverRequest,
    UpsertAlertReceiverResponse,
)
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user

router = APIRouter(prefix="/api/v1/agents", tags=["Agent Alert Receiver"])


# ── DI 플레이스홀더 (main.py 에서 override) ──────────────────────────


def get_get_alert_receiver_use_case():
    raise NotImplementedError


def get_upsert_alert_receiver_use_case():
    raise NotImplementedError


def get_rotate_alert_token_use_case():
    raise NotImplementedError


def get_list_alert_receipts_use_case():
    raise NotImplementedError


async def _run(call):
    try:
        return await call
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{agent_id}/alert-receiver", response_model=AlertReceiverConfigResponse)
async def get_alert_receiver(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_get_alert_receiver_use_case),
):
    request_id = str(uuid.uuid4())
    return await _run(use_case.execute(agent_id, str(current_user.id), request_id))


@router.put("/{agent_id}/alert-receiver", response_model=UpsertAlertReceiverResponse)
async def upsert_alert_receiver(
    agent_id: str,
    body: UpsertAlertReceiverRequest,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_upsert_alert_receiver_use_case),
):
    """없으면 생성(토큰 1회 반환), 있으면 지정한 필드만 수정."""
    request_id = str(uuid.uuid4())
    return await _run(
        use_case.execute(agent_id, str(current_user.id), body, request_id)
    )


@router.post(
    "/{agent_id}/alert-receiver/token", response_model=UpsertAlertReceiverResponse
)
async def rotate_alert_token(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_rotate_alert_token_use_case),
):
    request_id = str(uuid.uuid4())
    return await _run(use_case.execute(agent_id, str(current_user.id), request_id))


@router.get(
    "/{agent_id}/alert-receiver/receipts",
    response_model=list[AlertReceiptResponse],
)
async def list_alert_receipts(
    agent_id: str,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_list_alert_receipts_use_case),
):
    request_id = str(uuid.uuid4())
    return await _run(
        use_case.execute(agent_id, str(current_user.id), limit, request_id)
    )
