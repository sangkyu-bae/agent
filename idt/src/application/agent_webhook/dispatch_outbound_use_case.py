"""DispatchOutboundWebhookUseCase — outbound 발송 디스패처 (M2 Design §4-4).

앱 수명 싱글턴 (D11): AsyncSession을 보유하지 않고 session_factory로 짧은
트랜잭션 2개(설정 조회 / 이력 기록)만 연다 — HTTP 발송 구간은 세션 미보유.
inbound 비차단 태스크에서 응답 이후 실행될 수 있으므로 요청 스코프 자원 금지.

계약 (D16): dispatch()는 어떤 경우에도 raise하지 않는다 — 발송·이력 기록
실패는 로그로만 남기고 호출측(실행 경로)에 절대 전파하지 않는다.
"""
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent_webhook.entity import WebhookDelivery
from src.domain.agent_webhook.interfaces import OutboundSenderInterface
from src.domain.agent_webhook.policies import (
    WebhookOutboundPolicy,
    WebhookSignaturePolicy,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DispatchOutboundWebhookUseCase:
    def __init__(
        self,
        session_factory,
        webhook_repo_builder: Callable[[AsyncSession], object],
        delivery_repo_builder: Callable[[AsyncSession], object],
        sender: OutboundSenderInterface,
        logger: LoggerInterface,
    ) -> None:
        self._session_factory = session_factory
        self._webhook_repo_builder = webhook_repo_builder
        self._delivery_repo_builder = delivery_repo_builder
        self._sender = sender
        self._logger = logger

    async def dispatch(
        self, agent_id: str, run, triggered_by: str, request_id: str
    ) -> None:
        """run: RunAgentResponse 동형 (agent_id·query·answer·tools_used·session_id·run_id)."""
        try:
            await self._dispatch(agent_id, run, triggered_by, request_id)
        except Exception as e:
            # D16: 절대 재raise 금지 — 실행 경로 오염 차단
            self._logger.error(
                "outbound dispatch failed",
                exception=e,
                request_id=request_id,
                agent_id=agent_id,
                triggered_by=triggered_by,
            )

    async def _dispatch(
        self, agent_id: str, run, triggered_by: str, request_id: str
    ) -> None:
        webhook = await self._load_webhook(agent_id, request_id)
        if (
            webhook is None
            or not webhook.outbound_enabled
            or not webhook.outbound_url
        ):
            return  # D15: 비활성·미등록은 조용히 무발송 (이력 미기록)

        timestamp = int(time.time())
        body = self._build_payload(agent_id, run, triggered_by, timestamp)
        headers = {
            WebhookSignaturePolicy.HEADER_TIMESTAMP: str(timestamp),
            WebhookSignaturePolicy.HEADER_SIGNATURE: (
                WebhookSignaturePolicy.sign(webhook.secret, timestamp, body)
            ),
        }
        result = await self._sender.send(
            webhook.outbound_url, body, headers, request_id
        )
        await self._record_delivery(
            agent_id, run, webhook.outbound_url, triggered_by, result, request_id
        )
        self._logger.info(
            "outbound dispatched",
            request_id=request_id,
            agent_id=agent_id,
            triggered_by=triggered_by,
            success=result.success,
            attempts=result.attempts,
            status_code=result.status_code,
        )

    async def _load_webhook(self, agent_id: str, request_id: str):
        async with self._session_factory() as session:
            async with session.begin():
                repo = self._webhook_repo_builder(session)
                return await repo.find_by_agent_id(agent_id, request_id)

    def _build_payload(
        self, agent_id: str, run, triggered_by: str, timestamp: int
    ) -> bytes:
        payload = {
            "event": WebhookOutboundPolicy.EVENT_RUN_COMPLETED,
            "agent_id": agent_id,
            "run_id": getattr(run, "run_id", None),
            "session_id": getattr(run, "session_id", None),
            "query": getattr(run, "query", None),
            "answer": getattr(run, "answer", None),
            "tools_used": list(getattr(run, "tools_used", []) or []),
            "triggered_by": triggered_by,
            "timestamp": timestamp,
        }
        return json.dumps(payload, ensure_ascii=False).encode("utf-8")

    async def _record_delivery(
        self, agent_id, run, url, triggered_by, result, request_id
    ) -> None:
        delivery = WebhookDelivery(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            run_id=getattr(run, "run_id", None),
            url=url,
            trigger_source=triggered_by,
            success=result.success,
            status_code=result.status_code,
            attempts=result.attempts,
            error=result.error,
            duration_ms=result.duration_ms,
            created_at=_utc_now(),
        )
        async with self._session_factory() as session:
            async with session.begin():
                repo = self._delivery_repo_builder(session)
                await repo.insert(delivery, request_id)
