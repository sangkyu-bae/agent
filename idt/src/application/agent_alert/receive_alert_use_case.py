"""ReceiveAlertUseCase: Alertmanager 웹훅 수신 → 백그라운드 잡 등록.

Design Ref: firewall-agent design §2.2 (알림 경로) / §4.3.
- 인가는 Bearer 토큰 해시뿐이다. 설정 없음·토큰 불일치는 같은 AlertAuthError(401) —
  어떤 에이전트에 수신 설정이 있는지 드러내지 않는다.
- 인증 뒤에는 예외 대신 결과값으로 돌려주고(202) 이력 1행을 남긴다. Grafana 는 실패
응답을
  재전송하므로 깨진 본문·꺼짐·중복도 202 로 받아야 재전송 루프가 생기지 않는다.
- 실행은 하지 않는다. 잡을 등록하면 BackgroundJobWorker 가 소유자 신원으로 실행한다.
"""

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from src.application.agent_alert.schemas import ReceiveAlertResponse
from src.application.agent_automation.busy_checker import AgentBusyChecker
from src.domain.agent_alert.entity import (
    AlertReceipt,
    AlertReceiptResult,
    AlertReceiver,
)
from src.domain.agent_alert.interfaces import (
    AlertReceiptRepositoryInterface,
    AlertReceiverRepositoryInterface,
)
from src.domain.agent_alert.policies import (
    AlertBatch,
    AlertPayloadError,
    AlertPayloadPolicy,
    AlertTokenPolicy,
    render_instruction,
)
from src.domain.background_job.entity import BackgroundJob
from src.domain.background_job.interfaces import BackgroundJobRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_EMPTY_HASH = "0" * 64


class AlertAuthError(Exception):
    """토큰 없음·불일치·수신 설정 없음 — 구분하지 않는다 (401)."""


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ReceiveAlertUseCase:
    def __init__(
        self,
        receiver_repo: AlertReceiverRepositoryInterface,
        receipt_repo: AlertReceiptRepositoryInterface,
        job_repo: BackgroundJobRepositoryInterface,
        busy_checker: AgentBusyChecker,
        logger: LoggerInterface,
        dedupe_seconds: int,
        now_fn: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._receiver_repo = receiver_repo
        self._receipt_repo = receipt_repo
        self._job_repo = job_repo
        self._busy_checker = busy_checker
        self._logger = logger
        self._dedupe = timedelta(seconds=dedupe_seconds)
        self._now_fn = now_fn

    async def execute(
        self,
        agent_id: str,
        authorization: str | None,
        raw_body: bytes,
        request_id: str,
    ) -> ReceiveAlertResponse:
        receiver = await self._authenticate(agent_id, authorization, request_id)
        now = self._now_fn()
        try:
            batch = AlertPayloadPolicy.parse(json.loads(raw_body))
        except (ValueError, AlertPayloadError):
            return await self._record(
                receiver, None, now, "invalid_payload", request_id
            )

        result, reason = await self._decide(receiver, batch, now, request_id)
        job_id = None
        if result == "enqueued":
            job_id = await self._enqueue(receiver, batch, now, request_id)
        return await self._record(
            receiver, batch, now, result, request_id, skip_reason=reason, job_id=job_id
        )

    async def _authenticate(
        self, agent_id: str, authorization: str | None, request_id: str
    ) -> AlertReceiver:
        token = AlertTokenPolicy.bearer(authorization)
        receiver = await self._receiver_repo.find_by_agent_id(agent_id, request_id)
        if (
            token is None
            or receiver is None
            or not AlertTokenPolicy.verify(token, receiver.token_hash)
        ):
            self._logger.warning(
                "alert hook unauthorized", request_id=request_id, agent_id=agent_id
            )
            raise AlertAuthError("unauthorized")
        return receiver

    async def _decide(
        self,
        receiver: AlertReceiver,
        batch: AlertBatch,
        now: datetime,
        request_id: str,
    ) -> tuple[AlertReceiptResult, str | None]:
        """순서: 꺼짐 → 해소만 → 중복 → 바쁨 → 등록."""
        if not receiver.enabled:
            return "disabled", None
        if not batch.firing:
            return "resolved_only", None
        if await self._receipt_repo.exists_enqueued_since(
            receiver.id,
            batch.group_key_hash,
            batch.fingerprints_hash,
            now - self._dedupe,
            request_id,
        ):
            return "duplicate", None
        if receiver.skip_when_busy:
            verdict = await self._busy_checker.check(receiver.agent_id, request_id)
            if verdict.busy:
                return "skipped_busy", verdict.reason
        return "enqueued", None

    async def _enqueue(
        self,
        receiver: AlertReceiver,
        batch: AlertBatch,
        now: datetime,
        request_id: str,
    ) -> str:
        job = BackgroundJob(
            id=str(uuid.uuid4()),
            user_id=receiver.user_id,
            agent_id=receiver.agent_id,
            source="alert",
            query=render_instruction(receiver.instruction_prefix, batch.firing, now),
            session_id=None,
            run_id=None,
            status="queued",
            error_message=None,
            seen_at=None,
            queued_at=now,
            started_at=None,
            finished_at=None,
            request_id=request_id,
            created_at=now,
            updated_at=now,
        )
        await self._job_repo.enqueue(job, request_id)
        return job.id

    async def _record(
        self,
        receiver: AlertReceiver,
        batch: AlertBatch | None,
        now: datetime,
        result: AlertReceiptResult,
        request_id: str,
        *,
        skip_reason: str | None = None,
        job_id: str | None = None,
    ) -> ReceiveAlertResponse:
        receipt = AlertReceipt(
            id=str(uuid.uuid4()),
            receiver_id=receiver.id,
            agent_id=receiver.agent_id,
            group_key_hash=batch.group_key_hash if batch else _EMPTY_HASH,
            fingerprints_hash=batch.fingerprints_hash if batch else _EMPTY_HASH,
            firing_count=len(batch.firing) if batch else 0,
            result=result,
            skip_reason=skip_reason,
            job_id=job_id,
            received_at=now,
            request_id=request_id,
        )
        await self._receipt_repo.add(receipt, request_id)
        self._logger.info(
            "alert hook received",
            request_id=request_id,
            agent_id=receiver.agent_id,
            result=result,
            firing=receipt.firing_count,
            job_id=job_id,
        )
        return ReceiveAlertResponse(result=result, receipt_id=receipt.id, job_id=job_id)
