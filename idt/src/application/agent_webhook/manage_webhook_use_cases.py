"""agent-webhook 관리 UseCase 5종 (Design §4-3).

공통: ensure_owned_agent 소유자 검증 — 비소유자 PermissionError(403),
에이전트 미존재 ValueError(404). 시크릿 평문은 발급/rotate 응답에서만 노출.
"""
import uuid
from datetime import datetime, timezone

from src.application.agent_webhook.access import ensure_owned_agent
from src.application.agent_webhook.errors import WebhookValidationError
from src.application.agent_webhook.schemas import (
    UpdateWebhookRequest,
    WebhookConfigResponse,
    WebhookDeliveryResponse,
    WebhookSecretResponse,
    build_inbound_path,
)
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.agent_webhook.entity import AgentWebhook
from src.domain.agent_webhook.interfaces import AgentWebhookRepositoryInterface
from src.domain.agent_webhook.policies import (
    WebhookOutboundPolicy,
    WebhookSecretPolicy,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class EnableWebhookUseCase:
    """채널 생성 + 시크릿 발급. 기존재 시 ValueError('이미 …') → 409 (D6)."""

    def __init__(
        self,
        webhook_repo: AgentWebhookRepositoryInterface,
        agent_repo: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._webhook_repo = webhook_repo
        self._agent_repo = agent_repo
        self._logger = logger

    async def execute(
        self, agent_id: str, viewer_user_id: str, request_id: str
    ) -> WebhookSecretResponse:
        await ensure_owned_agent(
            self._agent_repo, agent_id, viewer_user_id, request_id
        )
        existing = await self._webhook_repo.find_by_agent_id(
            agent_id, request_id
        )
        if existing is not None:
            raise ValueError(
                "이미 활성화된 웹훅이 있습니다 — 재발급은 rotate를 사용하세요"
            )
        secret = WebhookSecretPolicy.generate()
        now = _utc_now()
        webhook = AgentWebhook(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            enabled=True,
            secret=secret,
            secret_hint=WebhookSecretPolicy.hint(secret),
            outbound_url=None,
            outbound_enabled=False,
            created_by=viewer_user_id,
            created_at=now,
            updated_at=now,
        )
        await self._webhook_repo.insert(webhook, request_id)
        self._logger.info(
            "webhook enabled", request_id=request_id, agent_id=agent_id
        )
        return WebhookSecretResponse(
            secret=secret,
            secret_hint=webhook.secret_hint,
            enabled=True,
            inbound_path=build_inbound_path(agent_id),
            created_at=now,
        )


class GetWebhookUseCase:
    """설정 조회 — 미설정 시 configured=False 응답 (404 아님, 프론트 분기 단순화)."""

    def __init__(
        self,
        webhook_repo: AgentWebhookRepositoryInterface,
        agent_repo: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._webhook_repo = webhook_repo
        self._agent_repo = agent_repo
        self._logger = logger

    async def execute(
        self, agent_id: str, viewer_user_id: str, request_id: str
    ) -> WebhookConfigResponse:
        await ensure_owned_agent(
            self._agent_repo, agent_id, viewer_user_id, request_id
        )
        webhook = await self._webhook_repo.find_by_agent_id(
            agent_id, request_id
        )
        if webhook is None:
            return WebhookConfigResponse(configured=False)
        return _to_config_response(webhook)


class RotateWebhookSecretUseCase:
    """시크릿 재발급 — 구키 즉시 무효 (저장 교체로 자동)."""

    def __init__(
        self,
        webhook_repo: AgentWebhookRepositoryInterface,
        agent_repo: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._webhook_repo = webhook_repo
        self._agent_repo = agent_repo
        self._logger = logger

    async def execute(
        self, agent_id: str, viewer_user_id: str, request_id: str
    ) -> WebhookSecretResponse:
        await ensure_owned_agent(
            self._agent_repo, agent_id, viewer_user_id, request_id
        )
        webhook = await self._webhook_repo.find_by_agent_id(
            agent_id, request_id
        )
        if webhook is None:
            raise ValueError(f"웹훅을 찾을 수 없습니다: {agent_id}")
        webhook.secret = WebhookSecretPolicy.generate()
        webhook.secret_hint = WebhookSecretPolicy.hint(webhook.secret)
        webhook.updated_at = _utc_now()
        await self._webhook_repo.update(webhook, request_id)
        self._logger.info(
            "webhook secret rotated", request_id=request_id, agent_id=agent_id
        )
        return WebhookSecretResponse(
            secret=webhook.secret,
            secret_hint=webhook.secret_hint,
            enabled=webhook.enabled,
            inbound_path=build_inbound_path(agent_id),
            created_at=webhook.created_at,
        )


class UpdateWebhookUseCase:
    """설정 변경 — enabled 토글(M1) + outbound URL/활성 (M2 D17).

    `model_fields_set`으로 "미지정 vs null(해제)"을 구분한다:
    - outbound_url=null 명시 → 해제 + outbound_enabled 강제 False
    - outbound_enabled=True는 URL 존재가 선행 조건 (위반 시 WebhookValidationError → 422)
    """

    def __init__(
        self,
        webhook_repo: AgentWebhookRepositoryInterface,
        agent_repo: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._webhook_repo = webhook_repo
        self._agent_repo = agent_repo
        self._logger = logger

    async def execute(
        self,
        agent_id: str,
        body: UpdateWebhookRequest,
        viewer_user_id: str,
        request_id: str,
    ) -> WebhookConfigResponse:
        await ensure_owned_agent(
            self._agent_repo, agent_id, viewer_user_id, request_id
        )
        webhook = await self._webhook_repo.find_by_agent_id(
            agent_id, request_id
        )
        if webhook is None:
            raise ValueError(f"웹훅을 찾을 수 없습니다: {agent_id}")

        self._apply_changes(webhook, body)
        webhook.updated_at = _utc_now()
        await self._webhook_repo.update(webhook, request_id)
        self._logger.info(
            "webhook updated",
            request_id=request_id,
            agent_id=agent_id,
            enabled=webhook.enabled,
            outbound_enabled=webhook.outbound_enabled,
        )
        return _to_config_response(webhook)

    @staticmethod
    def _apply_changes(webhook, body: UpdateWebhookRequest) -> None:
        fields = body.model_fields_set
        if "enabled" in fields and body.enabled is not None:
            webhook.enabled = body.enabled
        if "outbound_url" in fields:
            if body.outbound_url is None:
                webhook.outbound_url = None
                webhook.outbound_enabled = False
            else:
                if not WebhookOutboundPolicy.is_valid_url(body.outbound_url):
                    raise WebhookValidationError(
                        "outbound URL은 http/https 형식이어야 합니다"
                    )
                webhook.outbound_url = body.outbound_url
        if "outbound_enabled" in fields and body.outbound_enabled is not None:
            webhook.outbound_enabled = body.outbound_enabled
        if webhook.outbound_enabled and not webhook.outbound_url:
            raise WebhookValidationError("outbound URL을 먼저 등록하세요")


class ListWebhookDeliveriesUseCase:
    """outbound 발송 이력 조회 (M2 — 소유자 전용, created_at desc)."""

    def __init__(
        self,
        delivery_repo,
        agent_repo: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._delivery_repo = delivery_repo
        self._agent_repo = agent_repo
        self._logger = logger

    async def execute(
        self,
        agent_id: str,
        viewer_user_id: str,
        limit: int,
        request_id: str,
    ) -> list[WebhookDeliveryResponse]:
        await ensure_owned_agent(
            self._agent_repo, agent_id, viewer_user_id, request_id
        )
        deliveries = await self._delivery_repo.list_by_agent(
            agent_id, limit, request_id
        )
        return [
            WebhookDeliveryResponse(
                id=d.id,
                trigger_source=d.trigger_source,
                success=d.success,
                status_code=d.status_code,
                attempts=d.attempts,
                error=d.error,
                duration_ms=d.duration_ms,
                created_at=d.created_at,
            )
            for d in deliveries
        ]


class DisableWebhookUseCase:
    """채널 해제 (행 삭제 = 키 폐기, D7)."""

    def __init__(
        self,
        webhook_repo: AgentWebhookRepositoryInterface,
        agent_repo: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._webhook_repo = webhook_repo
        self._agent_repo = agent_repo
        self._logger = logger

    async def execute(
        self, agent_id: str, viewer_user_id: str, request_id: str
    ) -> None:
        await ensure_owned_agent(
            self._agent_repo, agent_id, viewer_user_id, request_id
        )
        webhook = await self._webhook_repo.find_by_agent_id(
            agent_id, request_id
        )
        if webhook is None:
            raise ValueError(f"웹훅을 찾을 수 없습니다: {agent_id}")
        await self._webhook_repo.delete(agent_id, request_id)
        self._logger.info(
            "webhook disabled", request_id=request_id, agent_id=agent_id
        )


def _to_config_response(webhook: AgentWebhook) -> WebhookConfigResponse:
    return WebhookConfigResponse(
        configured=True,
        enabled=webhook.enabled,
        secret_hint=webhook.secret_hint,
        inbound_path=build_inbound_path(webhook.agent_id),
        outbound_url=webhook.outbound_url,
        outbound_enabled=webhook.outbound_enabled,
        created_at=webhook.created_at,
    )
