"""SlotExtractor 테스트 — LLM 모의 (Design §3-3)."""
import json
from unittest.mock import MagicMock

import pytest

from src.domain.document_extractor.exceptions import SlotExtractionFailedError
from src.domain.document_extractor.schemas import TemplateSlot
from src.infrastructure.document_extractor.slot_extractor import SlotExtractor


class FakeLLM:
    """호출마다 contents를 순서대로 반환하는 모의 LLM."""

    def __init__(self, contents: list[str]):
        self._contents = list(contents)
        self.call_count = 0

    async def ainvoke(self, messages):
        self.call_count += 1
        content = self._contents.pop(0)
        response = MagicMock()
        response.content = content
        return response


class FakeLLMFactory:
    def __init__(self, llm):
        self._llm = llm

    def create(self, model, temperature):
        return self._llm


class FakeModelRepo:
    async def find_default(self, request_id):
        return MagicMock(id="m1", provider="openai", model_name="gpt-test")


def _extractor(contents: list[str]) -> tuple[SlotExtractor, FakeLLM]:
    llm = FakeLLM(contents)
    extractor = SlotExtractor(
        llm_factory=FakeLLMFactory(llm),
        llm_model_repository=FakeModelRepo(),
        logger=MagicMock(),
    )
    return extractor, llm

VALID_SLOTS_JSON = json.dumps([
    {"key": "loan_amount", "label": "여신금액", "slot_type": "value",
     "description": "", "fill_hint": "숫자+단위", "sample_value": "5억"},
    {"key": "opinion", "label": "소견", "slot_type": "generated"},
])


class TestExtract:
    @pytest.mark.asyncio
    async def test_valid_json_parsed_to_slots(self):
        extractor, _ = _extractor([VALID_SLOTS_JSON])
        result = await extractor.extract("<p>양식</p>", "req")
        assert [s.key for s in result.slots] == ["loan_amount", "opinion"]
        assert result.slots[1].slot_type == "generated"

    @pytest.mark.asyncio
    async def test_code_fence_stripped(self):
        extractor, _ = _extractor([f"```json\n{VALID_SLOTS_JSON}\n```"])
        result = await extractor.extract("<p>양식</p>", "req")
        assert len(result.slots) == 2

    @pytest.mark.asyncio
    async def test_invalid_slots_dropped_not_fatal(self):
        payload = json.dumps([
            {"key": "ok_key", "label": "정상", "slot_type": "value"},
            {"key": "BAD KEY", "label": "불량", "slot_type": "value"},
            {"key": "bad_type", "label": "타입불량", "slot_type": "magic"},
        ])
        extractor, _ = _extractor([payload])
        result = await extractor.extract("<p>양식</p>", "req")
        assert [s.key for s in result.slots] == ["ok_key"]

    @pytest.mark.asyncio
    async def test_duplicate_keys_deduped(self):
        payload = json.dumps([
            {"key": "dup", "label": "첫번째", "slot_type": "value"},
            {"key": "dup", "label": "두번째", "slot_type": "value"},
        ])
        extractor, _ = _extractor([payload])
        result = await extractor.extract("<p>양식</p>", "req")
        assert len(result.slots) == 1
        assert result.slots[0].label == "첫번째"

    @pytest.mark.asyncio
    async def test_parse_failure_retries_once_then_succeeds(self):
        extractor, llm = _extractor(["이건 JSON 아님", VALID_SLOTS_JSON])
        result = await extractor.extract("<p>양식</p>", "req")
        assert llm.call_count == 2
        assert len(result.slots) == 2

    @pytest.mark.asyncio
    async def test_parse_failure_twice_raises(self):
        extractor, llm = _extractor(["broken", "still broken"])
        with pytest.raises(SlotExtractionFailedError):
            await extractor.extract("<p>양식</p>", "req")
        assert llm.call_count == 2

    @pytest.mark.asyncio
    async def test_empty_array_is_valid(self):
        """슬롯 0개 = 실패 아님 (수동 지정 허용 — R2)."""
        extractor, _ = _extractor(["[]"])
        result = await extractor.extract("<p>양식</p>", "req")
        assert result.slots == []


class TestRefine:
    @pytest.mark.asyncio
    async def test_refine_includes_instruction_and_prev_slots(self):
        captured = {}

        class CapturingLLM(FakeLLM):
            async def ainvoke(self, messages):
                captured["prompt"] = str(messages)
                return await super().ainvoke(messages)

        llm = CapturingLLM([VALID_SLOTS_JSON])
        extractor = SlotExtractor(
            llm_factory=FakeLLMFactory(llm),
            llm_model_repository=FakeModelRepo(),
            logger=MagicMock(),
        )
        prev = [TemplateSlot(key="old_key", label="이전", slot_type="value")]
        result = await extractor.refine(
            "<p>양식</p>", "금액을 잘게 나눠줘", prev, "req"
        )
        assert len(result.slots) == 2
        assert "금액을 잘게 나눠줘" in captured["prompt"]
        assert "old_key" in captured["prompt"]
