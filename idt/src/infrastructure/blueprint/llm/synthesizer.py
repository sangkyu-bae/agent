"""NarrativeSynthesizer — 패턴 순서·제목 → NarrativeDraft.

Design Ref: golden-sample-blueprint §2.2 — 추출 단계는 비전 모델(어댑터)을 그대로 텍스트
LLM 으로 재사용한다(새 설정 키 0, D3). strict→json→text 폴백은 어댑터가 담당.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.domain.blueprint.schemas import NarrativeDraft
from src.domain.blueprint.value_objects import PagePattern
from src.infrastructure.blueprint.prompts import build_narrative_messages


class NarrativeSynthesizer:
    def __init__(self, adapter) -> None:
        self._adapter = adapter

    async def synthesize(
        self, patterns: Sequence[PagePattern], titles: Sequence[str], language: str
    ) -> NarrativeDraft:
        messages = build_narrative_messages(patterns, titles, language)
        outcome = await self._adapter.describe_with(messages, NarrativeDraft)
        return outcome.draft
