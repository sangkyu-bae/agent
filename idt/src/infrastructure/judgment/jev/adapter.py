"""Jev(TypeSafe System One) 어댑터 — `typesafe-sdk` AsyncTypeSafeClient 래핑.

Design Ref: judgment-backend §4.1 —
- 키·base_url·모델·타임아웃은 전부 명시 인자.
  환경변수(TYPESAFE_*)에 암묵 의존하지 않는다(FR-04).
- SDK 재시도는 끈다(D9) — 폴백이 있고 판정 지연 상한을 지켜야 한다.
- 요청 압축은 끈다 — 본문이 작고, zstd 미설치 환경(3.12)에서 기동 실패 가능성을 없앤다.
- `http_client` 주입
  (테스트: `httpx2.AsyncClient(transport=httpx2.MockTransport(...))`).
- 이 모듈을 import 하는 순간 `typesafe_sdk` 가 필요하다
  → 팩토리(module-3)의 ImportError 지점.
"""

from __future__ import annotations

import time
from collections.abc import Mapping

import httpx2
from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy, TypeSafeError

from src.domain.judgment.exceptions import JudgmentProtocolError
from src.domain.judgment.interfaces import JudgmentPort
from src.domain.judgment.value_objects import (
    JudgmentBackendKind,
    JudgmentRequest,
    JudgmentResponse,
)
from src.infrastructure.judgment.jev.mapping import (
    from_sdk_response,
    map_exception,
    to_sdk_questions,
)


class JevJudgmentAdapter(JudgmentPort):
    kind = JudgmentBackendKind.JEV

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float,
        base_url: str | None = None,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._model = model
        self._client = AsyncTypeSafeClient(
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout=timeout_seconds,
            retry=RetryPolicy(max_retries=0),
            compression=False,
            http_client=http_client,
        )

    async def judge(self, request: JudgmentRequest) -> JudgmentResponse:
        started = time.monotonic()
        state = (
            dict(request.state) if isinstance(request.state, Mapping) else request.state
        )
        try:
            response = await self._client.system_one(
                state,
                to_sdk_questions(request),
                model=self._model,
                timeout=self._timeout,
            )
        except TypeSafeError as e:
            raise map_exception(e, self._timeout) from e
        answers, extra = from_sdk_response(request, response)
        model = getattr(response, "model", None) or self._model
        if not isinstance(model, str) or not model:
            raise JudgmentProtocolError(self.kind, "response model is empty")
        return JudgmentResponse(
            answers=answers,
            model=model,
            backend=self.kind,
            latency_ms=int((time.monotonic() - started) * 1000),
            extra=extra,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
