"""agent-webhook 요청/응답 스키마 (Design §4-4)."""
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

INBOUND_PATH_TEMPLATE = "/api/v1/webhooks/agents/{agent_id}"


def build_inbound_path(agent_id: str) -> str:
    """프론트가 VITE_API_BASE_URL과 조합해 전체 수신 URL을 표시한다."""
    return INBOUND_PATH_TEMPLATE.format(agent_id=agent_id)


class WebhookInvokeRequest(BaseModel):
    """공개 inbound body — user_id는 받지 않는다 (D4: 서버가 소유자로 강제)."""

    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = None


class WebhookConfigResponse(BaseModel):
    """설정 조회 응답 — 미설정 시 configured=False, 나머지 None (Design D6)."""

    configured: bool
    enabled: bool | None = None
    secret_hint: str | None = None
    inbound_path: str | None = None
    outbound_url: str | None = None
    outbound_enabled: bool | None = None
    created_at: datetime | None = None


class WebhookSecretResponse(BaseModel):
    """발급/재발급 응답 — secret 평문은 이 응답에서만 노출 (1회)."""

    secret: str
    secret_hint: str
    enabled: bool
    inbound_path: str
    created_at: datetime


class UpdateWebhookRequest(BaseModel):
    """PATCH body — 전 필드 optional (M2 D17, additive).

    `outbound_url=null` 명시는 해제 의미 — 미지정과의 구분은
    use case가 `model_fields_set`으로 판별한다. 빈 body는 422 (M1 계약 유지).
    """

    enabled: bool | None = None
    outbound_url: str | None = None
    outbound_enabled: bool | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError("변경할 필드를 1개 이상 지정해야 합니다")
        return self


class WebhookDeliveryResponse(BaseModel):
    """outbound 발송 이력 행 (url은 노출 최소화로 제외 — Design §4-5)."""

    id: str
    trigger_source: str
    success: bool
    status_code: int | None
    attempts: int
    error: str | None
    duration_ms: int
    created_at: datetime
