"""Agent Webhook 관리 라우터 (JWT, 소유자 전용) — Design §4-4.

발급/rotate 응답의 secret 평문은 해당 응답 1회만 노출된다.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.agent_webhook.errors import WebhookValidationError
from src.application.agent_webhook.schemas import (
    UpdateWebhookRequest,
    WebhookConfigResponse,
    WebhookDeliveryResponse,
    WebhookSecretResponse,
)
from src.domain.auth.entities import User
from src.interfaces.dependencies.auth import get_current_user

router = APIRouter(prefix="/api/v1/agents", tags=["Agent Webhook"])


# ── DI 플레이스홀더 (main.py에서 override) ──────────────────────────

def get_enable_webhook_use_case():
    raise NotImplementedError


def get_get_webhook_use_case():
    raise NotImplementedError


def get_rotate_webhook_use_case():
    raise NotImplementedError


def get_update_webhook_use_case():
    raise NotImplementedError


def get_disable_webhook_use_case():
    raise NotImplementedError


def get_list_webhook_deliveries_use_case():
    raise NotImplementedError


def _map_value_error(e: ValueError) -> HTTPException:
    msg = str(e)
    if "이미" in msg:
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg)
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)


# ── 엔드포인트 ────────────────────────────────────────────────────


@router.post(
    "/{agent_id}/webhook",
    response_model=WebhookSecretResponse,
    status_code=status.HTTP_201_CREATED,
)
async def enable_webhook(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_enable_webhook_use_case),
):
    """웹훅 활성화 + 시크릿 발급 (평문은 이 응답 1회만)."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            agent_id, str(current_user.id), request_id
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise _map_value_error(e)


@router.get("/{agent_id}/webhook", response_model=WebhookConfigResponse)
async def get_webhook(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_get_webhook_use_case),
):
    """웹훅 설정 조회 — 미설정 시 configured=false (hint만, 평문 없음)."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            agent_id, str(current_user.id), request_id
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise _map_value_error(e)


@router.post(
    "/{agent_id}/webhook/rotate", response_model=WebhookSecretResponse
)
async def rotate_webhook_secret(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_rotate_webhook_use_case),
):
    """시크릿 재발급 — 기존 키 즉시 무효."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            agent_id, str(current_user.id), request_id
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise _map_value_error(e)


@router.patch("/{agent_id}/webhook", response_model=WebhookConfigResponse)
async def update_webhook(
    agent_id: str,
    body: UpdateWebhookRequest,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_update_webhook_use_case),
):
    """웹훅 설정 변경 — enabled 토글 + outbound URL/활성 (M2 D17)."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            agent_id, body, str(current_user.id), request_id
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except WebhookValidationError as e:
        # M2 D19: 설정 검증 실패는 전용 예외 → 422 (문자열 매칭 분기 아님)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e)
        )
    except ValueError as e:
        raise _map_value_error(e)


@router.get(
    "/{agent_id}/webhook/deliveries",
    response_model=list[WebhookDeliveryResponse],
)
async def list_webhook_deliveries(
    agent_id: str,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_list_webhook_deliveries_use_case),
):
    """outbound 발송 이력 조회 (최근순, 소유자 전용 — M2)."""
    request_id = str(uuid.uuid4())
    try:
        return await use_case.execute(
            agent_id, str(current_user.id), limit, request_id
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise _map_value_error(e)


@router.delete(
    "/{agent_id}/webhook", status_code=status.HTTP_204_NO_CONTENT
)
async def disable_webhook(
    agent_id: str,
    current_user: User = Depends(get_current_user),
    use_case=Depends(get_disable_webhook_use_case),
):
    """웹훅 채널 해제 (키 폐기 — 재활성화 시 신규 발급)."""
    request_id = str(uuid.uuid4())
    try:
        await use_case.execute(agent_id, str(current_user.id), request_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise _map_value_error(e)
