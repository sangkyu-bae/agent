"""agent_alert 저장소 (DB-001: commit/rollback 은 호출측 트랜잭션)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent_alert.entity import AlertReceipt, AlertReceiver
from src.domain.agent_alert.interfaces import (
    AlertReceiptRepositoryInterface,
    AlertReceiverRepositoryInterface,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.agent_alert.models import (
    AgentAlertReceiptModel,
    AgentAlertReceiverModel,
)

_RECEIVER_FIELDS = (
    "agent_id",
    "user_id",
    "enabled",
    "skip_when_busy",
    "token_hash",
    "token_hint",
    "instruction_prefix",
    "created_at",
    "updated_at",
)


def _receiver(model: AgentAlertReceiverModel) -> AlertReceiver:
    return AlertReceiver(
        id=model.id,
        agent_id=model.agent_id,
        user_id=model.user_id,
        enabled=bool(model.enabled),
        skip_when_busy=bool(model.skip_when_busy),
        token_hash=model.token_hash,
        token_hint=model.token_hint,
        instruction_prefix=model.instruction_prefix,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _receipt(model: AgentAlertReceiptModel) -> AlertReceipt:
    return AlertReceipt(
        id=model.id,
        receiver_id=model.receiver_id,
        agent_id=model.agent_id,
        group_key_hash=model.group_key_hash,
        fingerprints_hash=model.fingerprints_hash,
        firing_count=model.firing_count,
        result=model.result,  # type: ignore[arg-type]
        skip_reason=model.skip_reason,
        job_id=model.job_id,
        received_at=model.received_at,
        request_id=model.request_id,
    )


class AlertReceiverRepository(AlertReceiverRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def find_by_agent_id(
        self, agent_id: str, request_id: str
    ) -> AlertReceiver | None:
        result = await self._session.execute(
            select(AgentAlertReceiverModel).where(
                AgentAlertReceiverModel.agent_id == agent_id
            )
        )
        model = result.scalar_one_or_none()
        return _receiver(model) if model is not None else None

    async def save(self, receiver: AlertReceiver, request_id: str) -> None:
        model = AgentAlertReceiverModel(id=receiver.id)
        for field in _RECEIVER_FIELDS:
            setattr(model, field, getattr(receiver, field))
        self._session.add(model)
        await self._session.flush()
        self._logger.info(
            "alert receiver saved", request_id=request_id, agent_id=receiver.agent_id
        )

    async def update(self, receiver: AlertReceiver, request_id: str) -> None:
        model = await self._session.get(AgentAlertReceiverModel, receiver.id)
        if model is None:
            raise ValueError(f"알림 수신 설정을 찾을 수 없습니다: {receiver.id}")
        for field in _RECEIVER_FIELDS:
            setattr(model, field, getattr(receiver, field))
        await self._session.flush()


class AlertReceiptRepository(AlertReceiptRepositoryInterface):
    def __init__(self, session: AsyncSession, logger: LoggerInterface) -> None:
        self._session = session
        self._logger = logger

    async def add(self, receipt: AlertReceipt, request_id: str) -> None:
        self._session.add(
            AgentAlertReceiptModel(
                id=receipt.id,
                receiver_id=receipt.receiver_id,
                agent_id=receipt.agent_id,
                group_key_hash=receipt.group_key_hash,
                fingerprints_hash=receipt.fingerprints_hash,
                firing_count=receipt.firing_count,
                result=receipt.result,
                skip_reason=receipt.skip_reason,
                job_id=receipt.job_id,
                received_at=receipt.received_at,
                request_id=receipt.request_id,
            )
        )
        await self._session.flush()

    async def exists_enqueued_since(
        self,
        receiver_id: str,
        group_key_hash: str,
        fingerprints_hash: str,
        since: datetime,
        request_id: str,
    ) -> bool:
        result = await self._session.execute(
            select(AgentAlertReceiptModel.id)
            .where(
                AgentAlertReceiptModel.receiver_id == receiver_id,
                AgentAlertReceiptModel.group_key_hash == group_key_hash,
                AgentAlertReceiptModel.fingerprints_hash == fingerprints_hash,
                AgentAlertReceiptModel.result == "enqueued",
                AgentAlertReceiptModel.received_at > since,
            )
            .limit(1)
        )
        return result.first() is not None

    async def list_recent(
        self, receiver_id: str, limit: int, request_id: str
    ) -> list[AlertReceipt]:
        result = await self._session.execute(
            select(AgentAlertReceiptModel)
            .where(AgentAlertReceiptModel.receiver_id == receiver_id)
            .order_by(AgentAlertReceiptModel.received_at.desc())
            .limit(limit)
        )
        return [_receipt(m) for m in result.scalars().all()]
