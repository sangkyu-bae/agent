"""SlidePlanner — blueprint narrative 안에서 슬라이드 계획 (Design §2.2 / FR-12)."""

from __future__ import annotations

from collections.abc import Sequence

from langchain_core.messages import HumanMessage

from src.domain.blueprint.schemas import SlidePlanDraft
from src.domain.blueprint.value_objects import DocumentBlueprint
from src.infrastructure.blueprint.llm.structured import StructuredCaller
from src.infrastructure.blueprint.prompts_generation import build_plan_messages


class SlidePlanner:
    def __init__(self, llm, logger, callbacks=None) -> None:
        self._caller = StructuredCaller(llm, logger, callbacks)
        self.last_usage: dict | None = None

    async def plan(
        self,
        blueprint: DocumentBlueprint,
        topic: str,
        instruction: str,
        evidence: str,
        max_slides: int,
        feedback: Sequence[str] | None,
    ) -> SlidePlanDraft:
        messages = build_plan_messages(
            blueprint, topic, instruction, evidence, max_slides
        )
        if feedback:
            messages.append(
                HumanMessage(
                    content=(
                        "Previous plan was rejected for these reasons; fix them and "
                        "return a new plan using only existing pattern_ids:\n- "
                        + "\n- ".join(feedback)
                    )
                )
            )
        draft, _mode, usage = await self._caller.call(messages, SlidePlanDraft)
        self.last_usage = usage
        return draft  # type: ignore[return-value]
