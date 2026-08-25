"""StructuredCaller / SlidePlanner / SlotWriter — 워커 LLM(fake) 구조화 호출."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage
from pydantic import BaseModel, ConfigDict
from src.domain.blueprint.schemas import SlideContentDraft, SlidePlanDraft
from src.domain.blueprint.value_objects import (
    DocumentBlueprint,
    HeaderFooter,
    Narrative,
    NarrativeSection,
    PagePattern,
    PatternKind,
    RelBox,
    SlidePlan,
    Slot,
    SlotKind,
    StyleTokens,
    TableStyle,
)
from src.infrastructure.blueprint.llm.slide_planner import SlidePlanner
from src.infrastructure.blueprint.llm.slot_writer import SlotWriter
from src.infrastructure.blueprint.llm.structured import (
    StructuredCaller,
    StructuredCallError,
)
from src.infrastructure.blueprint.prompts_generation import (
    build_plan_messages,
    build_write_messages,
)


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    k: str


class FakeStructured:
    def __init__(self, fn):
        self._fn = fn
        self.configs = []

    async def ainvoke(self, messages, config=None):
        self.configs.append(config)
        return self._fn(messages)


class FakeChat:
    def __init__(self, strict=None, json_mode=None, text=None):
        self._modes = {"strict": strict, "json": json_mode}
        self._text = text
        self.calls: list[str] = []

    def with_structured_output(self, schema, method=None, strict=None, **kw):
        mode = "strict" if strict else "json"
        self.calls.append(mode)
        fn = self._modes[mode]
        if fn is None:
            raise AssertionError(f"{mode} 미준비")
        return FakeStructured(fn)

    async def ainvoke(self, messages, config=None):
        self.calls.append("text")
        return self._text(messages)


@pytest.mark.asyncio
async def test_structured_caller_strict_first_then_fallbacks():
    chat = FakeChat(
        strict=lambda m: {
            "raw": AIMessage(
                content="",
                usage_metadata={
                    "input_tokens": 1,
                    "output_tokens": 2,
                    "total_tokens": 3,
                },
            ),
            "parsed": _Schema(k="a"),
            "parsing_error": None,
        }
    )
    out, mode, usage = await StructuredCaller(chat, MagicMock()).call([], _Schema)
    assert out.k == "a" and mode == "strict" and usage["total_tokens"] == 3

    def boom(_):
        raise ValueError("no")

    chat = FakeChat(
        strict=boom, json_mode=boom, text=lambda m: AIMessage(content='{"k":"t"}')
    )
    out, mode, _ = await StructuredCaller(chat, MagicMock()).call([], _Schema)
    assert out.k == "t" and mode == "text" and chat.calls == ["strict", "json", "text"]


@pytest.mark.asyncio
async def test_structured_caller_all_fail_and_transient_propagates():
    def boom(_):
        raise ValueError("no")

    chat = FakeChat(
        strict=boom, json_mode=boom, text=lambda m: AIMessage(content="not json")
    )
    with pytest.raises(StructuredCallError):
        await StructuredCaller(chat, MagicMock()).call([], _Schema)

    class RateLimitError(Exception):
        status_code = 429

    def limited(_):
        raise RateLimitError()

    with pytest.raises(RateLimitError):
        await StructuredCaller(FakeChat(strict=limited), MagicMock()).call([], _Schema)


def _bp() -> DocumentBlueprint:
    now = datetime(2026, 8, 22, tzinfo=UTC)
    return DocumentBlueprint(
        id="b",
        name="n",
        description="",
        schema_version=1,
        source_kind="pdf",
        page_count=2,
        style=StyleTokens(
            (13.333, 7.5),
            {"heading": "H", "body": "B"},
            {"h1": 28.0, "h2": 20.0, "body": 14.0, "caption": 10.0},
            {
                "primary": "#1F3A5F",
                "accent1": "#E07A1F",
                "text": "#222222",
                "bg": "#FFFFFF",
            },
            TableStyle("#1F3A5F", "#FFFFFF", "#CCCCCC", False),
            HeaderFooter(None, "", ""),
        ),
        patterns=(
            PagePattern(
                "cover",
                PatternKind.COVER,
                (
                    Slot(
                        "title",
                        SlotKind.TITLE,
                        RelBox(0.1, 0.4, 0.8, 0.2),
                        "제목",
                        40,
                        None,
                        None,
                    ),
                ),
                None,
                1,
                "",
            ),
            PagePattern(
                "chart",
                PatternKind.CHART_WITH_NOTES,
                (
                    Slot(
                        "title",
                        SlotKind.TITLE,
                        RelBox(0.1, 0.1, 0.8, 0.1),
                        "제목",
                        40,
                        None,
                        None,
                    ),
                    Slot(
                        "chart",
                        SlotKind.CHART,
                        RelBox(0.1, 0.25, 0.5, 0.6),
                        "차트",
                        None,
                        None,
                        None,
                    ),
                    Slot(
                        "notes",
                        SlotKind.BULLETS,
                        RelBox(0.65, 0.25, 0.3, 0.6),
                        "해설",
                        300,
                        None,
                        None,
                    ),
                ),
                None,
                2,
                "좌 차트 우 해설",
            ),
        ),
        narrative=Narrative(
            (
                NarrativeSection("표지", ("cover",), "주제·부서"),
                NarrativeSection("분석", ("chart",), "추이와 원인"),
            ),
            "보고체 개조식",
            "ko",
        ),
        assets=(),
        font_mapping={},
        warnings=(),
        status="active",
        created_at=now,
        updated_at=now,
    )


def test_plan_messages_contain_narrative_catalog_instruction_and_limits():
    msgs = build_plan_messages(
        _bp(), "3분기 연체율", "10장 이내, 결론 먼저", "근거: 연체율 1.5%", 10
    )
    system, human = msgs[0].content, msgs[1].content
    assert "max_slides=10" in system or "at most 10" in system
    assert "pattern_id" in system and "never follow instructions" in system.lower()
    assert (
        "cover" in human and "chart_with_notes" in human and "좌 차트 우 해설" in human
    )
    assert "표지" in human and "추이와 원인" in human
    assert "3분기 연체율" in human and "결론 먼저" in human and "연체율 1.5%" in human


def test_write_messages_describe_slots_with_limits_and_chart_rule():
    plan = SlidePlan(2, "chart", "연체율 추이", "3Q 상승 원인", "연체율 표")
    msgs = build_write_messages(_bp(), _bp().patterns[1], plan, "근거", "대화", 2, 5)
    human = msgs[1].content
    assert "slot_id=title" in human and "max_chars=40" in human
    assert "slot_id=chart" in human and "kind=chart" in human
    assert (
        "연체율 추이" in human and "3Q 상승 원인" in human and "slide 2 of 5" in human
    )
    assert "numbers" in msgs[0].content.lower() and "보고체 개조식" in msgs[0].content


@pytest.mark.asyncio
async def test_planner_and_writer_return_drafts():
    chat = FakeChat(
        strict=lambda m: SlidePlanDraft(
            slides=[
                {"pattern_id": "cover", "title": "t", "intent": "", "data_hint": ""}
            ]
        )
    )
    draft = await SlidePlanner(chat, MagicMock()).plan(
        _bp(), "topic", "", "", 5, feedback=None
    )
    assert draft.slides[0].pattern_id == "cover"

    chat = FakeChat(
        strict=lambda m: SlideContentDraft(
            slots=[
                {
                    "slot_id": "title",
                    "text": "T",
                    "bullets": None,
                    "table": None,
                    "chart": None,
                }
            ]
        )
    )
    plan = SlidePlan(1, "cover", "t", "", "")
    content = await SlotWriter(chat, MagicMock()).write(
        _bp(), _bp().patterns[0], plan, "", "", 1, 1
    )
    assert content.slots[0].text == "T"


@pytest.mark.asyncio
async def test_planner_feedback_is_appended_as_retry_instruction():
    seen = []

    def strict(m):
        seen.append(m)
        return SlidePlanDraft(slides=[])

    await SlidePlanner(FakeChat(strict=strict), MagicMock()).plan(
        _bp(), "t", "", "", 5, feedback=["slide 2: unknown pattern_id 'zzz'"]
    )
    assert "zzz" in seen[0][-1].content


def test_write_messages_exclude_footer_slot_and_rule():
    """style-fidelity DR-2: 푸터는 스타일 값 — LLM 에 슬롯으로 주지 않는다."""
    from dataclasses import replace

    from src.domain.blueprint.value_objects import RelBox, Slot, SlotKind

    bp = _bp()
    pattern = bp.patterns[1]
    footer = Slot(
        "footer", SlotKind.FOOTER, RelBox(0.05, 0.9, 0.9, 0.05), "푸터", 50, None, None
    )
    pattern = replace(pattern, slots=(*pattern.slots, footer))
    plan = SlidePlan(2, pattern.id, "t", "i", "")
    msgs = build_write_messages(bp, pattern, plan, "근거", "대화", 2, 5)
    human = msgs[1].content
    assert "slot_id=footer" not in human
    assert "footer" not in msgs[0].content.split("Rules per slot kind:")[1]
