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
        self.configs: list[dict | None] = []

    async def ainvoke(self, messages, config=None):
        self.call_count += 1
        self.configs.append(config)
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


class TestLlmFailure:
    """LLM 호출 실패(429 등)는 도메인 예외로 감싸 라우터가 메시지를 전달하게 한다."""

    @pytest.mark.asyncio
    async def test_llm_error_wrapped_as_domain_error(self):
        class FailingLLM:
            async def ainvoke(self, messages, config=None):
                raise RuntimeError(
                    "Error code: 429 - rate_limit_exceeded: Request too large"
                )

        extractor = SlotExtractor(
            llm_factory=FakeLLMFactory(FailingLLM()),
            llm_model_repository=FakeModelRepo(),
            logger=MagicMock(),
        )
        with pytest.raises(SlotExtractionFailedError) as exc_info:
            await extractor.extract("<p>양식</p>", "req")
        assert "429" in str(exc_info.value)


class TestHtmlClip:
    """LLM 입력 HTML 상한 — TPM 한도 초과(429) 방지."""

    @pytest.mark.asyncio
    async def test_long_html_clipped_before_llm(self):
        captured = {}

        class CapturingLLM(FakeLLM):
            async def ainvoke(self, messages, config=None):
                captured["user"] = messages[1]["content"]
                return await super().ainvoke(messages, config=config)

        extractor = SlotExtractor(
            llm_factory=FakeLLMFactory(CapturingLLM([VALID_SLOTS_JSON])),
            llm_model_repository=FakeModelRepo(),
            logger=MagicMock(),
            llm_html_max_chars=100,
        )
        await extractor.extract("<p>" + "가" * 500 + "</p>", "req")
        assert "가" * 500 not in captured["user"]
        assert "이하 생략" in captured["user"]

    @pytest.mark.asyncio
    async def test_short_html_not_clipped(self):
        extractor, llm = _extractor([VALID_SLOTS_JSON])
        await extractor.extract("<p>짧은 양식</p>", "req")
        assert llm.call_count == 1


class TestLangsmithTrace:
    """LangSmith 추적 config — run_name/tags/metadata 주입 (per-run tracer 패턴)."""

    @pytest.mark.asyncio
    async def test_extract_passes_trace_config(self):
        extractor, llm = _extractor([VALID_SLOTS_JSON])
        await extractor.extract("<p>양식</p>", "req-1")
        config = llm.configs[0]
        assert config is not None
        assert config["run_name"] == "slot-extract"
        assert "document-extractor" in config["tags"]
        assert config["metadata"]["request_id"] == "req-1"

    @pytest.mark.asyncio
    async def test_refine_passes_trace_config(self):
        extractor, llm = _extractor([VALID_SLOTS_JSON])
        await extractor.refine("<p>양식</p>", "보강해줘", [], "req-2")
        config = llm.configs[0]
        assert config is not None
        assert config["run_name"] == "slot-refine"
        assert config["metadata"]["request_id"] == "req-2"


class TestRefine:
    @pytest.mark.asyncio
    async def test_refine_includes_instruction_and_prev_slots(self):
        captured = {}

        class CapturingLLM(FakeLLM):
            async def ainvoke(self, messages, config=None):
                captured["prompt"] = str(messages)
                return await super().ainvoke(messages, config=config)

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
