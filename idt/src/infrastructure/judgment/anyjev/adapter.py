"""AnyJev HTTP 어댑터 — `POST {base_url}/v1/decide`.

Design Ref: judgment-backend §4.2 / D10 —
- httpx 타임아웃 → JudgmentTimeoutError, 전송 오류·4xx/5xx → JudgmentUnavailableError,
  JSON·스키마·확률 위반 → JudgmentProtocolError. 예외를 삼키지 않는다(FR-08).
- 서버는 인증이 없고 model 을 응답에 주지 않는다 → `model_name` 설정값을 표기(D4).
- 클라이언트는 앱 수명 싱글턴, `aclose()` 로 정리(D15). 테스트는 `transport` 주입.
"""

from __future__ import annotations

import time

import httpx

from src.domain.judgment.exceptions import (
    JudgmentProtocolError,
    JudgmentTimeoutError,
    JudgmentUnavailableError,
)
from src.domain.judgment.interfaces import JudgmentPort
from src.domain.judgment.value_objects import (
    JudgmentBackendKind,
    JudgmentRequest,
    JudgmentResponse,
)
from src.infrastructure.judgment.anyjev.mapping import from_decisions, to_items

_DECIDE_PATH = "/v1/decide"


class AnyJevJudgmentAdapter(JudgmentPort):
    kind = JudgmentBackendKind.ANYJEV

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        model_name: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._model_name = model_name or "anyjev"
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            transport=transport,
        )

    async def judge(self, request: JudgmentRequest) -> JudgmentResponse:
        started = time.monotonic()
        payload = {"items": to_items(request)}
        try:
            response = await self._client.post(_DECIDE_PATH, json=payload)
        except httpx.TimeoutException as e:
            raise JudgmentTimeoutError(self.kind, self._timeout) from e
        except httpx.RequestError as e:
            # Check G1: TransportError 뿐 아니라 DecodingError 등 RequestError 전체
            raise JudgmentUnavailableError(self.kind, type(e).__name__) from e
        if response.status_code >= 400:
            raise JudgmentUnavailableError(
                self.kind, "server error", status=response.status_code
            )
        body = self._parse_json(response)
        answers, extras = from_decisions(request, body.get("decisions"))
        return JudgmentResponse(
            answers=answers,
            model=self._model_name,
            backend=self.kind,
            latency_ms=int((time.monotonic() - started) * 1000),
            extra={"decisions": extras},
        )

    def _parse_json(self, response: httpx.Response) -> dict:
        try:
            body = response.json()
        except ValueError as e:
            raise JudgmentProtocolError(self.kind, "response is not JSON") from e
        if not isinstance(body, dict):
            raise JudgmentProtocolError(self.kind, "response is not an object")
        return body

    async def aclose(self) -> None:
        await self._client.aclose()
