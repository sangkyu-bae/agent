"""답변 노드용 인용 서비스 (answer-citation-verification §2.1, D-10~D-12).

답변 노드(WorkflowCompiler)는 duck typing 으로만 쓴다:
  run = service.begin()            # 이 실행에 번호 붙은 청크가 없으면 None
  run.instruction / run.strip_history(text) / run.request_for(text)
  text = await run.finalize(text, verdict, request, request_id=...)
저장 실패는 답변을 막지 않는다(fail-open). 로그에 문장·근거 원문을 싣지 않는다.
"""

from __future__ import annotations

from typing import Any

from src.application.agent_run.context import get_current_run_context
from src.application.answer_citation.registry import CitationRegistry
from src.domain.answer_citation.instruction import FinalAnswerCitationPolicy
from src.domain.answer_citation.models import RegisteredChunk
from src.domain.answer_citation.parser import CitationMarkerParser
from src.domain.answer_citation.policy import CitationFinalizePolicy
from src.domain.hallucination.citation_check import CitationCheckRequest
from src.domain.hallucination.grounding import GroundingVerdict
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class CitationService:
    def __init__(
        self, registry: CitationRegistry, store: Any, logger: LoggerInterface
    ) -> None:
        self._registry = registry
        self._store = store  # save(run_id, outcome, *, judge_model, request_id)
        self._logger = logger

    def begin(self) -> CitationRun | None:
        ctx = get_current_run_context()
        if ctx is None or ctx.run_id is None:
            return None
        run_id = str(ctx.run_id.value)
        chunks = self._registry.chunks(run_id)
        if not chunks:
            return None
        return CitationRun(run_id, chunks, self._registry, self._store, self._logger)


class CitationRun:
    def __init__(
        self,
        run_id: str,
        chunks: dict[int, RegisteredChunk],
        registry: CitationRegistry,
        store: Any,
        logger: LoggerInterface,
    ) -> None:
        self._run_id = run_id
        self._chunks = chunks
        self._registry = registry
        self._store = store
        self._logger = logger

    @property
    def instruction(self) -> str:
        return FinalAnswerCitationPolicy.instruction()

    @staticmethod
    def strip_history(text: str) -> str:
        """이전 답변의 인용 표시 제거 — 지난 턴 번호가 이번 번호와 섞이지 않게(D-10)."""
        return CitationMarkerParser.strip_all(text)

    def request_for(self, text: str) -> CitationCheckRequest | None:
        """판정할 본문의 인용 쌍과 인용된 청크 원문(D-03). 인용이 없으면 None."""
        pairs = CitationMarkerParser.pairs(
            CitationMarkerParser.normalize(text), self._chunks
        )
        if not pairs:
            return None
        cited = {p.marker: self._chunks[p.marker].text for p in pairs}
        return CitationCheckRequest(pairs=pairs, cited_sources=cited)

    async def finalize(
        self,
        text: str,
        verdict: GroundingVerdict | None,
        request: CitationCheckRequest | None,
        *,
        request_id: str,
    ) -> str:
        outcome = CitationFinalizePolicy.finalize(
            text,
            chunks=self._chunks,
            pairs=request.pairs if request is not None else (),
            checks=verdict.citation_checks if verdict is not None else (),
            judged=verdict is not None,
        )
        try:
            await self._store.save(
                self._run_id, outcome, judge_model=None, request_id=request_id
            )
        except Exception as e:  # noqa: BLE001 — 저장 실패는 답변을 막지 않는다
            self._logger.warning(
                "answer citation save failed",
                request_id=request_id,
                run_id=self._run_id,
                exception=e,
            )
        self._registry.discard(self._run_id)
        self._logger.info(
            "answer citations finalized",
            request_id=request_id,
            run_id=self._run_id,
            status=outcome.status,
            none_reason=outcome.none_reason,
            citation_count=len(outcome.citations),
            chunk_count=len(self._chunks),
        )
        return outcome.text
