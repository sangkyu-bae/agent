"""알림 수신 설정 관리 UseCase 4종 — firewall-agent design §4.1.

공통: 소유자 검사 — 비소유자 PermissionError(403), 에이전트 없음 ValueError(404).
토큰 평문은 최초 생성·재발급 응답에서만 1회 노출한다(저장은 sha256 해시).
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from src.application.agent_alert.access import ensure_owned_agent
from src.application.agent_alert.schemas import (
    AlertReceiptResponse,
    AlertReceiverConfigResponse,
    UpsertAlertReceiverRequest,
    UpsertAlertReceiverResponse,
)
from src.domain.agent_alert.entity import AlertReceiver
from src.domain.agent_alert.interfaces import (
    AlertReceiptRepositoryInterface,
    AlertReceiverRepositoryInterface,
)
from src.domain.agent_alert.policies import AlertTokenPolicy
from src.domain.agent_builder.interfaces import AgentDefinitionRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface

RECEIPTS_LIMIT_MAX = 100


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class _Base:
    def __init__(
        self,
        receiver_repo: AlertReceiverRepositoryInterface,
        agent_repo: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
        now_fn: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._receiver_repo = receiver_repo
        self._agent_repo = agent_repo
        self._logger = logger
        self._now_fn = now_fn

    async def _owned_receiver(
        self, agent_id: str, user_id: str, request_id: str
    ) -> AlertReceiver | None:
        await ensure_owned_agent(self._agent_repo, agent_id, user_id, request_id)
        return await self._receiver_repo.find_by_agent_id(agent_id, request_id)


class GetAlertReceiverUseCase(_Base):
    async def execute(
        self, agent_id: str, user_id: str, request_id: str
    ) -> AlertReceiverConfigResponse:
        return AlertReceiverConfigResponse.of(
            await self._owned_receiver(agent_id, user_id, request_id)
        )


class UpsertAlertReceiverUseCase(_Base):
    async def execute(
        self,
        agent_id: str,
        user_id: str,
        request: UpsertAlertReceiverRequest,
        request_id: str,
    ) -> UpsertAlertReceiverResponse:
        existing = await self._owned_receiver(agent_id, user_id, request_id)
        now = self._now_fn()
        if existing is None:
            return await self._create(agent_id, user_id, request, now, request_id)
        if request.enabled is not None:
            existing.enabled = request.enabled
        if request.skip_when_busy is not None:
            existing.skip_when_busy = request.skip_when_busy
        if request.instruction_prefix is not None:
            existing.instruction_prefix = request.instruction_prefix.strip()
        existing.updated_at = now
        await self._receiver_repo.update(existing, request_id)
        self._logger.info(
            "alert receiver updated",
            request_id=request_id,
            agent_id=agent_id,
            enabled=existing.enabled,
        )
        return UpsertAlertReceiverResponse(
            config=AlertReceiverConfigResponse.of(existing)
        )

    async def _create(
        self,
        agent_id: str,
        user_id: str,
        request: UpsertAlertReceiverRequest,
        now: datetime,
        request_id: str,
    ) -> UpsertAlertReceiverResponse:
        token = AlertTokenPolicy.generate()
        receiver = AlertReceiver(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            user_id=user_id,
            enabled=bool(request.enabled),
            skip_when_busy=(
                True if request.skip_when_busy is None else request.skip_when_busy
            ),
            token_hash=AlertTokenPolicy.hash(token),
            token_hint=AlertTokenPolicy.hint(token),
            instruction_prefix=(request.instruction_prefix or "").strip(),
            created_at=now,
            updated_at=now,
        )
        await self._receiver_repo.save(receiver, request_id)
        self._logger.info(
            "alert receiver created", request_id=request_id, agent_id=agent_id
        )
        return UpsertAlertReceiverResponse(
            config=AlertReceiverConfigResponse.of(receiver), token=token
        )


class RotateAlertTokenUseCase(_Base):
    async def execute(
        self, agent_id: str, user_id: str, request_id: str
    ) -> UpsertAlertReceiverResponse:
        receiver = await self._owned_receiver(agent_id, user_id, request_id)
        if receiver is None:
            raise LookupError("알림 수신 설정이 없습니다")
        token = AlertTokenPolicy.generate()
        receiver.token_hash = AlertTokenPolicy.hash(token)
        receiver.token_hint = AlertTokenPolicy.hint(token)
        receiver.updated_at = self._now_fn()
        await self._receiver_repo.update(receiver, request_id)
        self._logger.info(
            "alert receiver token rotated", request_id=request_id, agent_id=agent_id
        )
        return UpsertAlertReceiverResponse(
            config=AlertReceiverConfigResponse.of(receiver), token=token
        )


class ListAlertReceiptsUseCase:
    def __init__(
        self,
        receiver_repo: AlertReceiverRepositoryInterface,
        receipt_repo: AlertReceiptRepositoryInterface,
        agent_repo: AgentDefinitionRepositoryInterface,
        logger: LoggerInterface,
    ) -> None:
        self._receiver_repo = receiver_repo
        self._receipt_repo = receipt_repo
        self._agent_repo = agent_repo
        self._logger = logger

    async def execute(
        self, agent_id: str, user_id: str, limit: int, request_id: str
    ) -> list[AlertReceiptResponse]:
        await ensure_owned_agent(self._agent_repo, agent_id, user_id, request_id)
        receiver = await self._receiver_repo.find_by_agent_id(agent_id, request_id)
        if receiver is None:
            return []
        rows = await self._receipt_repo.list_recent(
            receiver.id, max(1, min(limit, RECEIPTS_LIMIT_MAX)), request_id
        )
        return [AlertReceiptResponse.of(r) for r in rows]
