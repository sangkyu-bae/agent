"""SlotWriter — 슬라이드 1장의 슬롯 내용 작성 (Design D5 / FR-13)."""

from __future__ import annotations

from src.domain.blueprint.schemas import SlideContentDraft
from src.domain.blueprint.value_objects import (
    DocumentBlueprint,
    PagePattern,
    SlidePlan,
)
from src.infrastructure.blueprint.llm.structured import StructuredCaller
from src.infrastructure.blueprint.prompts_generation import build_write_messages


class SlotWriter:
    def __init__(self, llm, logger, callbacks=None) -> None:
        self._caller = StructuredCaller(llm, logger, callbacks)
        self.usages: list[dict] = []

    async def write(
        self,
        blueprint: DocumentBlueprint,
        pattern: PagePattern,
        plan: SlidePlan,
        evidence: str,
        conversation: str,
        index: int,
        total: int,
    ) -> SlideContentDraft:
        messages = build_write_messages(
            blueprint, pattern, plan, evidence, conversation, index, total
        )
        draft, _mode, usage = await self._caller.call(messages, SlideContentDraft)
        if usage:
            self.usages.append(usage)
        return draft  # type: ignore[return-value]
