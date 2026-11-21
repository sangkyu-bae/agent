"""근거 재작성 루프 — 생성 → 판정 → (사유 넣어) 재작성 → 상한 초과 시 문장 제거.

Design Ref: draft-grounding-check v0.2 §2.2, §5.1.

action 초안 작성 노드와 final_answer 가 같은 루프를 쓴다(중복 구현 0).
- 재작성 대상은 severity=high 주장만 (D-05)
- 판정 실패는 원문 유지 — 답변·초안을 막지 않는다 (D-06, fail-open)
- 상한 초과 시 판정기가 인용한 구간이 든 문장 제거. 초안이 비면 빈 문자열
  (호출측이 작성 실패 처리), 답변이 비면 원문 유지 (D-07)
- 근거 없음·설정 off·판정기 미주입이면 판정 0회 (D-09)
로그에는 주장·값 원문을 싣지 않는다.
"""
import traceback
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal


from src.domain.hallucination.citation_check import CitationCheckRequest
from src.domain.hallucination.grounding import GroundingJudgePort, GroundingVerdict
from src.domain.hallucination.grounding_edit import GroundingEditPolicy
from src.domain.hallucination.grounding_hints import GroundingHintPolicy
from src.domain.logging.interfaces.logger_interface import LoggerInterface

Target = Literal["draft", "answer"]
Generate = Callable[[str], Awaitable[str]]
# answer-citation-verification S7: 판정할 본문 → 인용 검증 요청(인용이 없으면 None)
CitationBuilder = Callable[[str], CitationCheckRequest | None]


@dataclass(frozen=True)
class GroundedResult:
    text: str
    attempts: int  # 생성 호출 수
    stripped: bool
    judged: bool  # 판정이 한 번이라도 성공했는가
    # answer-citation-verification D-06: 마지막으로 성공한 판정과 그때의 인용 요청
    verdict: GroundingVerdict | None = None
    citation_request: CitationCheckRequest | None = None


class GroundedGenerator:
    def __init__(
        self, judge: GroundingJudgePort | None, logger: LoggerInterface,
        *, enabled: bool, corpus_max_chars: int,
    ) -> None:
        self._judge = judge
        self._logger = logger
        self._enabled = enabled
        self._corpus_max_chars = corpus_max_chars

    @property
    def active(self) -> bool:
        return self._enabled and self._judge is not None

    async def run(
        self, *, generate: Generate, question: str, sources: str,
        max_retries: int, target: Target, request_id: str,
        citations: CitationBuilder | None = None,
    ) -> GroundedResult:
        text = await generate("")
        reason = self._skip_reason(sources)
        if reason:
            self._logger.debug(
                "grounding skipped", target=target, request_id=request_id, reason=reason,
            )
            return GroundedResult(text, 1, False, False)
        attempts, judged, last = 1, False, {}
        for attempt in range(max_retries + 1):
            request = self._citation_request(citations, text, request_id)
            verdict = await self._judge_safely(
                question, sources, text, target, request_id, request
            )
            if verdict is None:
                return GroundedResult(text, attempts, False, judged, **last)
            judged = True
            last = {"verdict": verdict, "citation_request": request}
            high = verdict.high_claims
            if not high:
                return GroundedResult(text, attempts, False, True, **last)
            if attempt == max_retries:
                return self._strip(text, high, attempts, target, request_id, last)
            regenerated = await self._regenerate(generate, text, high, target, request_id)
            if regenerated is None:
                return self._strip(text, high, attempts, target, request_id, last)
            text, attempts = regenerated, attempts + 1
        return GroundedResult(text, attempts, False, judged, **last)

    async def verify_citations(
        self, *, question: str, sources: str, text: str,
        request: CitationCheckRequest | None, request_id: str,
    ) -> GroundingVerdict | None:
        """재작성 없이 인용만 1회 판정 (answer-citation-verification D-05).

        근거 판정이 꺼져 있어도 인용 기능이 켜져 있으면 쓴다. 판정기가 없거나
        요청이 비었거나 실패하면 None (fail-open — 답변은 그대로).
        """
        if self._judge is None or request is None or request.empty:
            return None
        return await self._judge_safely(
            question, sources, text, "answer", request_id, request
        )

    def _citation_request(
        self, citations: CitationBuilder | None, text: str, request_id: str
    ) -> CitationCheckRequest | None:
        if citations is None:
            return None
        try:
            return citations(text)
        except Exception as e:  # noqa: BLE001 — 인용 요청 실패는 기존 판정으로
            self._logger.warning(
                "citation request build failed", request_id=request_id,
                exception_type=type(e).__name__,
            )
            return None

    def _skip_reason(self, sources: str) -> str:
        if not self._enabled:
            return "disabled"
        if self._judge is None:
            return "no_judge"
        if not (sources or "").strip():
            return "no_sources"
        return ""

    async def _judge_safely(
        self, question: str, sources: str, text: str, target: Target, request_id: str,
        citations: CitationCheckRequest | None = None,
    ) -> GroundingVerdict | None:
        hints = GroundingHintPolicy.unfound_values(text, sources)
        kwargs = {}
        if citations is not None and not citations.empty:
            kwargs["citations"] = citations  # 없으면 기존 호출 그대로(D-04)
        try:
            verdict = await self._judge.judge(
                question=question, sources=sources[: self._corpus_max_chars],
                generation=text, hints=hints, request_id=request_id, **kwargs,
            )
        except Exception as e:
            # D-06: fail-open — 원문을 그대로 쓴다. 초안은 승인 게이트가 최종 방어선.
            # Analysis G-2/G-12: 실패 로그는 여기 한 곳. 메시지는 싣지 않는다 —
            # 구조화 출력 파싱 오류면 판정기 원출력(주장 구간)이 메시지에 실린다.
            self._logger.warning(
                "grounding judge failed", target=target, request_id=request_id,
                exception_type=type(e).__name__,
                stack="".join(traceback.format_tb(e.__traceback__)),
            )
            return None
        filtered = verdict.excluding_found_in(sources)
        self._logger.info(
            "grounding judged", target=target, request_id=request_id,
            high_count=len(filtered.high_claims),
            low_count=len(filtered.unsupported_claims) - len(filtered.high_claims),
            literal_dropped=len(verdict.unsupported_claims) - len(filtered.unsupported_claims),
            hint_count=len(hints),
        )
        return filtered

    async def _regenerate(
        self, generate: Generate, text: str, high, target: Target, request_id: str,
    ) -> str | None:
        self._logger.info("grounding regenerated", target=target, request_id=request_id)
        try:
            return await generate(GroundingEditPolicy.feedback(text, high))
        except Exception as e:
            self._logger.warning(
                "grounding regeneration failed", target=target, request_id=request_id,
                exception=e,
            )
            return None

    def _strip(
        self, text: str, high, attempts: int, target: Target, request_id: str,
        last: dict | None = None,
    ) -> GroundedResult:
        last = last or {}
        stripped = GroundingEditPolicy.strip_sentences(text, high)
        if stripped == text:
            # 판정기가 원문에 없는 구간을 인용 — 오삭제 없이 원문 유지.
            return GroundedResult(text, attempts, False, True, **last)
        if not stripped.strip() and target == "answer":
            # D-07: 채팅 답변은 빈 응답 금지 — 원문 유지.
            self._logger.warning(
                "grounding strip left empty answer — original kept",
                target=target, request_id=request_id,
            )
            return GroundedResult(text, attempts, False, True, **last)
        self._logger.warning(
            "grounding sentences stripped", target=target, request_id=request_id,
            removed_count=len(high),
        )
        return GroundedResult(stripped, attempts, True, True, **last)
