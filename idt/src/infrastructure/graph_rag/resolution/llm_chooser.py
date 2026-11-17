"""LlmEntityChooser — Jev 재판정(가운데 구간)·대체(Jev 불가) 판정자.

Design Ref: graph-rag-foundation §7.2 D4·D5 / Plan FR-09. 재판정 모델은 설정의
rejudge 모델(없으면 추출 모델). 목록 밖 라벨은 NEW·low 로 바꿔 검토 대기로 보낸다.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from src.domain.graph_rag.extraction import Mention
from src.domain.graph_rag.interfaces import EntityChooserPort, GraphSettingsReaderPort
from src.domain.graph_rag.resolution import (
    NEW_LABEL,
    Candidate,
    ChooserVerdict,
    LlmConfidence,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_SYSTEM = (
    "당신은 지식 그래프의 엔티티 중복을 판정합니다.\n"
    "문서의 '언급'이 후보 중 어느 엔티티와 같은 대상인지 고릅니다.\n"
    "- 표기·띄어쓰기·약칭만 다르면 같은 대상입니다.\n"
    "- 이름이 비슷해도 가리키는 대상이 다르면(다른 상품·규정·기준) NEW 입니다.\n"
    "- 확신이 없으면 confidence 를 medium 또는 low 로 답합니다.\n"
    "- reason 은 한 문장으로 씁니다."
)


class EntityChoiceOutput(BaseModel):
    label: str = Field(description="후보 라벨(C1, C2, ...) 또는 NEW")
    confidence: Literal["high", "medium", "low"] = Field(description="판정 확신도")
    reason: str = Field(default="", description="한 문장 근거")


_NEW_HINT = "후보 중 같은 대상이 없음"


def _prompt(
    mention: Mention,
    context: str,
    candidates: dict[str, Candidate],
    system: str = _SYSTEM,
    new_hint: str = _NEW_HINT,
):
    lines = [
        f"{label}: {c.name} (타입: {c.type})"
        + (f" — {c.description[:200]}" if c.description else "")
        for label, c in candidates.items()
    ]
    mention_line = f"[언급] {mention.name} (타입: {mention.type})"
    if mention.description:
        mention_line += f" — {mention.description[:200]}"
    user = (
        f"{mention_line}\n"
        f"[문맥] {context}\n\n[후보]\n"
        + "\n".join(lines)
        + f"\n{NEW_LABEL}: {new_hint}"
    )
    return [("system", system), ("human", user)]


class LlmEntityChooser(EntityChooserPort):
    """시스템 문구만 바꿔 주제 판정(module-4b)에도 쓴다 — system·new_hint."""

    def __init__(
        self,
        llm_model_repo: Any,
        llm_factory: Any,
        reader: GraphSettingsReaderPort,
        logger: LoggerInterface,
        *,
        system: str = _SYSTEM,
        new_hint: str = _NEW_HINT,
    ) -> None:
        self._repo = llm_model_repo
        self._factory = llm_factory
        self._reader = reader
        self._logger = logger
        self._system = system
        self._new_hint = new_hint
        self._llms: dict[str, Any] = {}

    async def _structured(self, request_id: str) -> Any:
        model_id = (await self._reader.get()).effective_rejudge_model_id
        if not model_id:
            raise ValueError("rejudge/extraction llm model not configured")
        if model_id not in self._llms:
            model = await self._repo.find_by_id(model_id, request_id)
            if model is None:
                raise ValueError(f"rejudge llm model not found: {model_id}")
            llm = self._factory.create(model, 0.0)
            self._llms[model_id] = llm.with_structured_output(EntityChoiceOutput)
        return self._llms[model_id]

    async def choose(
        self,
        mention: Mention,
        context: str,
        candidates: dict[str, Candidate],
        request_id: str,
    ) -> ChooserVerdict:
        structured = await self._structured(request_id)
        out: EntityChoiceOutput = await structured.ainvoke(
            _prompt(mention, context, candidates, self._system, self._new_hint)
        )
        label = (out.label or "").strip().upper()
        if label != NEW_LABEL and label not in candidates:
            return ChooserVerdict(
                NEW_LABEL,
                confidence=LlmConfidence.LOW,
                reason=f"unknown label {out.label!r}",
            )
        return ChooserVerdict(
            label,
            confidence=LlmConfidence(out.confidence),
            reason=(out.reason or "").strip() or None,
        )
