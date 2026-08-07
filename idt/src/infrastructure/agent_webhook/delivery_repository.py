"""AgentWebhookDeliveryRepository: 발송 이력 저장소 (INSERT only, D20).

commit/rollback 호출 금지 — 트랜잭션 경계는 호출측이 소유한다 (DB-001).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent_webhook.entity import WebhookDelivery
from src.domain.agent_webhook.interfaces import (
    AgentWebhookDeliveryRepositoryInterface,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.agent_webhook.models import AgentWebhookDeliveryModel


def _to_entity(model: AgentWebhookDeliveryModel) -> WebhookDelivery:
    return WebhookDelivery(
        id=model.id,
        agent_id=model.agent_id,
        run_id=model.run_id,
        url=model.url,
        trigger_source=model.trigger_source,
        success=model.success,
        status_code=model.status_code,
        attempts=model.attempts,
        error=model.error,
        duration_ms=model.duration_ms,
        created_at=model.created_at,
    )


class AgentWebhookDeliveryRepository(AgentWebhookDeliveryRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def insert(self, delivery: WebhookDelivery, request_id: str) -> None:
        model = AgentWebhookDeliveryModel(
            id=delivery.id,
            agent_id=delivery.agent_id,
            run_id=delivery.run_id,
            url=delivery.url,
            trigger_source=delivery.trigger_source,
            success=delivery.success,
            status_code=delivery.status_code,
            attempts=delivery.attempts,
            error=delivery.error,
            duration_ms=delivery.duration_ms,
            created_at=delivery.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        self._logger.info(
            "agent_webhook_delivery inserted",
            request_id=request_id,
            agent_id=delivery.agent_id,
            success=delivery.success,
            attempts=delivery.attempts,
        )

    async def list_by_agent(
        self, agent_id: str, limit: int, request_id: str
    ) -> list[WebhookDelivery]:
        stmt = (
            select(AgentWebhookDeliveryModel)
            .where(AgentWebhookDeliveryModel.agent_id == agent_id)
            .order_by(AgentWebhookDeliveryModel.created_at.desc())
            .limit(limit)
        )
        models = (await self._session.execute(stmt)).scalars().all()
        return [_to_entity(m) for m in models]
