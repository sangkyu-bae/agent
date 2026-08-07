"""HttpxOutboundSender — outbound 웹훅 HTTP 발송기 (M2 Design §4-3).

- 재시도 정책은 WebhookOutboundPolicy(D13): 총 4회(최초 1+재시도 3) · 백오프 1/2/4s
  · 5xx/연결오류만 재시도 · 2xx만 성공.
- 시크릿·서명·body는 로그 인자로 전달하지 않는다 (url·status_code·attempts만).
- transport/sleep 주입은 테스트용 (MockTransport · 무대기 sleep).
"""
import asyncio
import time

import httpx

from src.domain.agent_webhook.interfaces import (
    OutboundResult,
    OutboundSenderInterface,
)
from src.domain.agent_webhook.policies import WebhookOutboundPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class HttpxOutboundSender(OutboundSenderInterface):
    def __init__(
        self,
        logger: LoggerInterface,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep=asyncio.sleep,
    ) -> None:
        self._logger = logger
        self._transport = transport
        self._sleep = sleep

    async def send(
        self, url: str, body: bytes, headers: dict, request_id: str
    ) -> OutboundResult:
        start = time.monotonic()
        total_attempts = 1 + WebhookOutboundPolicy.MAX_RETRIES
        attempts = 0
        status_code: int | None = None
        error: str | None = None
        success = False

        while attempts < total_attempts:
            attempts += 1
            status_code, error = await self._attempt(url, body, headers)
            if status_code is not None and 200 <= status_code < 300:
                success = True
                error = None
                break
            if attempts >= total_attempts:
                break
            if not WebhookOutboundPolicy.should_retry(status_code):
                break
            await self._sleep(
                WebhookOutboundPolicy.BACKOFF_SECONDS[attempts - 1]
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        self._logger.info(
            "outbound send done",
            request_id=request_id,
            url=url,
            success=success,
            status_code=status_code,
            attempts=attempts,
        )
        return OutboundResult(
            success=success,
            status_code=status_code,
            attempts=attempts,
            error=error,
            duration_ms=duration_ms,
        )

    async def _attempt(
        self, url: str, body: bytes, headers: dict
    ) -> tuple[int | None, str | None]:
        try:
            async with httpx.AsyncClient(
                timeout=WebhookOutboundPolicy.REQUEST_TIMEOUT_SECONDS,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    url,
                    content=body,
                    headers={**headers, "Content-Type": "application/json"},
                )
            if 200 <= response.status_code < 300:
                return response.status_code, None
            return response.status_code, f"HTTP {response.status_code}"
        except Exception as e:
            # Check G8: httpx.HTTPError 외 예외(InvalidURL 등)도 시도 실패로
            # 흡수해야 delivery 이력이 일관되게 남는다 (dispatch 외곽 유출 방지).
            message = str(e)[: WebhookOutboundPolicy.ERROR_MESSAGE_MAX]
            return None, message or type(e).__name__
