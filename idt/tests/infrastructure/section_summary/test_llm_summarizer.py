"""LlmSectionSummarizer 테스트 — structured output + JSON 폴백 (Design D10)."""
import json

import pytest

from src.domain.section_summary.entities import SectionCard
from src.infrastructure.section_summary.llm_summarizer import (
    LlmSectionSummarizer,
    SectionSummaryOutput,
    SectionSummarizeError,
)


class _FakeLogger:
    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...
    def critical(self, *a, **k): ...


class _StructuredRunnable:
    def __init__(self, output):
        self._output = output

    async def ainvoke(self, messages):
        if isinstance(self._output, Exception):
            raise self._output
        return self._output


class _FakeLlm:
    """with_structured_output 경로와 일반 ainvoke(JSON 폴백) 경로를 모두 흉내."""

    def __init__(self, structured=None, raw_contents=None):
        self._structured = structured
        self._raw_contents = list(raw_contents or [])
        self.raw_calls = 0

    def with_structured_output(self, schema):
        if isinstance(self._structured, Exception):
            raise self._structured
        return _StructuredRunnable(self._structured)

    async def ainvoke(self, messages):
        self.raw_calls += 1
        if not self._raw_contents:
            raise AssertionError("unexpected raw ainvoke")
        content = self._raw_contents.pop(0)

        class _Resp:
            pass

        resp = _Resp()
        resp.content = content
        return resp


def _card() -> SectionCard:
    return SectionCard(
        section_ref="parent-1",
        title="제1조 (목적)",
        text="이 규정은 여신 업무의 기준을 정함을 목적으로 한다.",
    )


@pytest.mark.asyncio
async def test_structured_output_success():
    llm = _FakeLlm(
        structured=SectionSummaryOutput(
            keywords=["여신", "규정"], summary_lines=["a", "b", "c"]
        )
    )
    summarizer = LlmSectionSummarizer(llm, _FakeLogger(), input_char_cap=12000)
    result = await summarizer.summarize(_card(), "req-1")
    assert result.keywords == ["여신", "규정"]
    assert result.summary_lines == ["a", "b", "c"]
    assert llm.raw_calls == 0


@pytest.mark.asyncio
async def test_fallback_to_json_when_structured_fails():
    payload = json.dumps(
        {"keywords": ["대출"], "summary_lines": ["한 줄", "두 줄", "세 줄"]},
        ensure_ascii=False,
    )
    llm = _FakeLlm(
        structured=RuntimeError("function calling unsupported"),
        raw_contents=[f"```json\n{payload}\n```"],
    )
    summarizer = LlmSectionSummarizer(llm, _FakeLogger(), input_char_cap=12000)
    result = await summarizer.summarize(_card(), "req-1")
    assert result.keywords == ["대출"]
    assert llm.raw_calls == 1


@pytest.mark.asyncio
async def test_fallback_when_structured_returns_empty_lines():
    payload = json.dumps({"keywords": ["k"], "summary_lines": ["l1"]})
    llm = _FakeLlm(
        structured=SectionSummaryOutput(keywords=[], summary_lines=[]),
        raw_contents=[payload],
    )
    summarizer = LlmSectionSummarizer(llm, _FakeLogger(), input_char_cap=12000)
    result = await summarizer.summarize(_card(), "req-1")
    assert result.summary_lines == ["l1"]


@pytest.mark.asyncio
async def test_json_parse_retries_once_then_raises():
    llm = _FakeLlm(
        structured=RuntimeError("no structured"),
        raw_contents=["not json", "still not json"],
    )
    summarizer = LlmSectionSummarizer(llm, _FakeLogger(), input_char_cap=12000)
    with pytest.raises(SectionSummarizeError):
        await summarizer.summarize(_card(), "req-1")
    assert llm.raw_calls == 2


@pytest.mark.asyncio
async def test_input_is_capped():
    captured: dict = {}

    class _CapturingRunnable:
        async def ainvoke(self, messages):
            captured["user"] = messages[1]["content"]
            return SectionSummaryOutput(keywords=["k"], summary_lines=["a"])

    class _CapturingLlm:
        def with_structured_output(self, schema):
            return _CapturingRunnable()

    card = SectionCard(section_ref="p", title="t", text="가" * 500)
    summarizer = LlmSectionSummarizer(
        _CapturingLlm(), _FakeLogger(), input_char_cap=100
    )
    await summarizer.summarize(card, "req-1")
    assert "가" * 101 not in captured["user"]
