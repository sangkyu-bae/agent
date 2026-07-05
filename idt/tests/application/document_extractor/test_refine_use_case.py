"""RefineSlotsUseCase 테스트 — 재추천 + MAX_REGEN 상한 (Design §3-2)."""
from unittest.mock import MagicMock

import pytest

from src.application.document_extractor.refine_use_case import RefineSlotsUseCase
from src.application.document_extractor.schemas import TemplateSlotDto
from src.domain.document_extractor.exceptions import RegenLimitExceededError
from src.domain.document_extractor.schemas import SuggestedSlots, TemplateSlot


class FakeExtractor:
    def __init__(self):
        self.refine_args = None

    async def refine(self, html, instruction, prev_slots, request_id):
        self.refine_args = dict(
            html=html, instruction=instruction, prev_slots=prev_slots
        )
        return SuggestedSlots(
            slots=[TemplateSlot(key="new_key", label="새슬롯", slot_type="value")]
        )


class TestRefineSlotsUseCase:
    @pytest.mark.asyncio
    async def test_refine_returns_new_suggestions(self):
        extractor = FakeExtractor()
        uc = RefineSlotsUseCase(
            slot_extractor=extractor, logger=MagicMock(), max_regen=10
        )
        result = await uc.execute(
            html="<p>양식</p>",
            instruction="금액 나눠줘",
            prev_slots=[
                TemplateSlotDto(key="old_key", label="이전", slot_type="value")
            ],
            regen_count=1,
            request_id="req",
        )
        assert result.suggested_slots[0].key == "new_key"
        # 프론트 DTO → 도메인 슬롯 변환 확인
        assert extractor.refine_args["prev_slots"][0].key == "old_key"

    @pytest.mark.asyncio
    async def test_regen_limit_enforced(self):
        uc = RefineSlotsUseCase(
            slot_extractor=FakeExtractor(), logger=MagicMock(), max_regen=3
        )
        with pytest.raises(RegenLimitExceededError):
            await uc.execute(
                html="<p>양식</p>", instruction="x", prev_slots=[],
                regen_count=3, request_id="req",
            )
