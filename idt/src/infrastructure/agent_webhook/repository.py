"""AgentWebhookRepository: agent_webhook 저장소.

commit/rollback 호출 금지 — 트랜잭션 경계는 호출측(get_session dependency)이
소유한다 (DB-001, agent_schedule 선례).
"""
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent_webhook.entity import AgentWebhook
from src.domain.agent_webhook.interfaces import AgentWebhookRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.agent_webhook.models import AgentWebhookModel


def _to_entity(model: AgentWebhookModel) -> AgentWebhook:
    return AgentWebhook(
        id=model.id,
        agent_id=model.agent_id,
        enabled=model.enabled,
        secret=model.secret,
        secret_hint=model.secret_hint,
        outbound_url=model.outbound_url,
        outbound_enabled=model.outbound_enabled,
        created_by=model.created_by,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class AgentWebhookRepository(AgentWebhookRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def find_by_agent_id(
        self, agent_id: str, request_id: str
    ) -> AgentWebhook | None:
        stmt = select(AgentWebhookModel).where(
            AgentWebhookModel.agent_id == agent_id
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_entity(model) if model is not None else None

    async def insert(self, webhook: AgentWebhook, request_id: str) -> None:
        model = AgentWebhookModel(
            id=webhook.id,
            agent_id=webhook.agent_id,
            enabled=webhook.enabled,
            secret=webhook.secret,
            secret_hint=webhook.secret_hint,
            outbound_url=webhook.outbound_url,
            outbound_enabled=webhook.outbound_enabled,
            created_by=webhook.created_by,
            created_at=webhook.created_at,
            updated_at=webhook.updated_at,
        )
        self._session.add(model)
        await self._session.flush()
        self._logger.info(
            "agent_webhook inserted",
            request_id=request_id,
            agent_id=webhook.agent_id,
        )

    async def update(self, webhook: AgentWebhook, request_id: str) -> None:
        stmt = select(AgentWebhookModel).where(
            AgentWebhookModel.agent_id == webhook.agent_id
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            raise ValueError(f"웹훅을 찾을 수 없습니다: {webhook.agent_id}")
        model.enabled = webhook.enabled
        model.secret = webhook.secret
        model.secret_hint = webhook.secret_hint
        model.outbound_url = webhook.outbound_url
        model.outbound_enabled = webhook.outbound_enabled
        model.updated_at = webhook.updated_at
        await self._session.flush()
        self._logger.info(
            "agent_webhook updated",
            request_id=request_id,
            agent_id=webhook.agent_id,
        )

    async def delete(self, agent_id: str, request_id: str) -> None:
        await self._session.execute(
            delete(AgentWebhookModel).where(
                AgentWebhookModel.agent_id == agent_id
            )
        )
        self._logger.info(
            "agent_webhook deleted", request_id=request_id, agent_id=agent_id
        )
