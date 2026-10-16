"""웹 검색 필요 판단 — 판정 백엔드(Jev/AnyJev) 어댑터 + 기존 LLM 폴백.

Design Ref: judgment-backend §4.5 —
- Noul 1개(`questions.SEARCH_DECISION_NOUL`) → `probability >= threshold` (D13).
- 포트 예외(`JudgmentError`)·외부 타임아웃은 여기서만 삼키고 주입된 `fallback`
  (기존 `LLMSearchDecisionAdapter`)을 그대로 호출한다 — "없던 상태" = 기존 동작(FR-11).
- state 원문은 로그에 싣지 않는다(FR-14). 길이·해시 앞 12자·확률·지연만.
- `asyncio.wait_for` 는 단일 코루틴에만 쓴다(제너레이터 아님). `+0.5` 는 어댑터 내부
  타임아웃이 먼저 발동하게 두는 외부 안전망.
"""

from __future__ import annotations

import asyncio
import hashlib

from src.domain.judgment.exceptions import JudgmentError
from src.domain.judgment.interfaces import JudgmentPort
from src.domain.judgment.value_objects import JudgmentRequest, NoulQuestion
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.search_decision.interfaces import SearchDecisionInterface
from src.domain.search_decision.schemas import WebSearchDecision
from src.infrastructure.search_decision.questions import QID, SEARCH_DECISION_NOUL

_OUTER_TIMEOUT_MARGIN = 0.5


class JudgmentSearchDecisionAdapter(SearchDecisionInterface):
    """판정 백엔드로 결정하고, 실패하면 fallback 어댑터 결과를 그대로 돌려준다."""

    def __init__(
        self,
        backend: JudgmentPort,
        fallback: SearchDecisionInterface,
        threshold: float,
        timeout_seconds: float,
        logger: LoggerInterface,
    ) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be within [0, 1]")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        self._backend = backend
        self._fallback = fallback
        self._threshold = threshold
        self._timeout = timeout_seconds
        self._logger = logger

    async def decide(
        self, question: str, analysis_text: str, request_id: str
    ) -> WebSearchDecision:
        request = JudgmentRequest(
            state={"question": question, "analysis_text": analysis_text},
            questions={QID: NoulQuestion(SEARCH_DECISION_NOUL)},
        )
        try:
            response = await asyncio.wait_for(
                self._backend.judge(request), self._timeout + _OUTER_TIMEOUT_MARGIN
            )
            probability = response.noul(QID).probability
        except (TimeoutError, JudgmentError) as e:
            # Plan SC: 백엔드 실패 시 폴백 100% — 기존 LLM 판정 경로로 그대로.
            self._logger.warning(
                "judgment failed, falling back to LLM search decision",
                exception=e,
                backend=self._backend.kind.value,
                request_id=request_id,
            )
            return await self._fallback.decide(question, analysis_text, request_id)
        self._logger.debug(
            "judgment search decision",
            backend=response.backend.value,
            model=response.model,
            latency_ms=response.latency_ms,
            probability=round(probability, 3),
            state_chars=len(question) + len(analysis_text),
            state_hash=_digest(question, analysis_text),
            request_id=request_id,
        )
        return WebSearchDecision(
            needs_web_search=probability >= self._threshold,
            reason=(
                f"judgment:{response.backend.value} "
                f"p={probability:.2f} thr={self._threshold:.2f}"
            ),
        )


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:12]
