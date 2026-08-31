"""PresentationGenerationUseCase (Design §2.2 생성 / §6.3 degraded / FR-12~15)."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from pptx import Presentation
from src.application.blueprint.generation_use_case import (
    PresentationGenerationUseCase,
)
from src.domain.agent_attachment.value_objects import AttachmentType, StoredAttachment
from src.domain.blueprint.errors import PresentationGenerateError
from src.domain.blueprint.schemas import SlideContentDraft, SlidePlanDraft
from src.domain.blueprint.tool_config import PresentationGeneratorToolConfig
from src.domain.blueprint.value_objects import (
    DocumentBlueprint,
    HeaderFooter,
    Narrative,
    NarrativeSection,
    PagePattern,
    PatternKind,
    RelBox,
    Slot,
    SlotKind,
    StyleTokens,
    TableStyle,
)
from src.infrastructure.blueprint.renderer.pptx_renderer import PptxSlideRenderer


def _bp() -> DocumentBlueprint:
    now = datetime(2026, 8, 22, tzinfo=UTC)
    return DocumentBlueprint(
        id="b",
        name="리스크보고",
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
            HeaderFooter(None, "{n}/{total}", ""),
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
                        60,
                        None,
                        None,
                    ),
                ),
                None,
                2,
                "",
            ),
        ),
        narrative=Narrative(
            (
                NarrativeSection("표지", ("cover",), ""),
                NarrativeSection("분석", ("chart",), ""),
            ),
            "보고체",
            "ko",
        ),
        assets=(),
        font_mapping={"H": "NanumGothicBold", "B": "NanumGothic"},
        warnings=(),
        status="active",
        created_at=now,
        updated_at=now,
    )


def _plan(*items) -> SlidePlanDraft:
    return SlidePlanDraft(
        slides=[
            {"pattern_id": p, "title": t, "intent": "", "data_hint": ""}
            for p, t in items
        ]
    )


class FakePlanner:
    def __init__(self, drafts):
        self.drafts = list(drafts)
        self.feedbacks = []
        self.last_usage = {"total_tokens": 10}

    async def plan(self, blueprint, topic, instruction, evidence, max_slides, feedback):
        self.feedbacks.append(feedback)
        return self.drafts.pop(0)


class FakeWriter:
    def __init__(self, fail_index: int | None = None, long_notes=False):
        self.fail_index = fail_index
        self.long_notes = long_notes
        self.calls = []
        self.usages = [{"total_tokens": 5}]

    async def write(
        self, blueprint, pattern, plan, evidence, conversation, index, total
    ):
        self.calls.append((index, total, pattern.id))
        if index == self.fail_index:
            raise ValueError("writer boom")
        slots = [
            {
                "slot_id": "title",
                "text": plan.title,
                "bullets": None,
                "table": None,
                "chart": None,
            }
        ]
        if pattern.id == "chart":
            slots.append(
                {
                    "slot_id": "chart",
                    "text": None,
                    "bullets": None,
                    "table": None,
                    "chart": {
                        "type": "bar",
                        "categories": ["1Q", "2Q"],
                        "series": [{"name": "r", "values": [1.0, 2.0]}],
                        "unit": None,
                    },
                }
            )
            notes = ["x" * 100] if self.long_notes else ["상승", "SME"]
            slots.append(
                {
                    "slot_id": "notes",
                    "text": None,
                    "bullets": notes,
                    "table": None,
                    "chart": None,
                }
            )
        return SlideContentDraft(slots=slots)


class FakeStore:
    def __init__(self):
        self.saved = []

    def save(self, *, file_bytes, filename, attachment_type, owner_user_id):
        self.saved.append((filename, file_bytes, attachment_type, owner_user_id))
        return StoredAttachment(
            file_id=f"f{len(self.saved)}",
            type=attachment_type,
            filename=filename,
            size=len(file_bytes),
            owner_user_id=owner_user_id,
            file_path="/tmp/x",
        )


class FakeConverter:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    async def to_pdf_from_pptx(self, pptx_bytes, mcp_tool_id, request_id):
        self.calls.append(mcp_tool_id)
        if self.fail:
            raise RuntimeError("mcp down")
        return b"%PDF-fake"


def _uc(planner, writer, store=None, converter=None, concurrency=2):
    return PresentationGenerationUseCase(
        planner_factory=lambda llm, cb: planner,
        writer_factory=lambda llm, cb: writer,
        renderer=PptxSlideRenderer(),
        store=store or FakeStore(),
        converter=converter,
        logger=MagicMock(),
        concurrency=concurrency,
        input_max_chars=50,
    )


def _cfg(**over):
    base = dict(
        blueprint_id="b",
        output_format="pptx",
        mcp_pptx_to_pdf_tool_id="",
        max_slides=15,
    )
    base.update(over)
    return PresentationGeneratorToolConfig(**base)


async def _run(uc, cfg=None, instruction="", evidence="근거", conversation="대화"):
    return await uc.generate(
        llm=MagicMock(),
        blueprint=_bp(),
        assets={},
        tool_config=cfg or _cfg(),
        evidence_block=evidence,
        conversation_block=conversation,
        user_instruction=instruction,
        owner_user_id="u1",
        request_id="r1",
    )


@pytest.mark.asyncio
async def test_happy_path_plans_writes_renders_and_stores():
    planner = FakePlanner([_plan(("cover", "3Q 리스크"), ("chart", "연체율"))])
    writer = FakeWriter()
    store = FakeStore()
    out = await _run(_uc(planner, writer, store))
    assert out.slide_count == 2 and out.chart_count == 1 and out.pdf_file_id is None
    assert (
        out.filename == "리스크보고.pptx" and out.file_id == "f1" and out.warnings == ()
    )
    assert out.usage["total_tokens"] == 15
    name, data, atype, owner = store.saved[0]
    assert atype is AttachmentType.DOCUMENT and owner == "u1"
    prs = Presentation(io.BytesIO(data))
    assert len(prs.slides) == 2
    assert sorted(writer.calls) == [(1, 2, "cover"), (2, 2, "chart")]
    assert planner.feedbacks == [None]


@pytest.mark.asyncio
async def test_invalid_plan_retried_once_with_feedback_then_rejected_dropped():
    planner = FakePlanner(
        [
            _plan(("cover", "a"), ("nope", "b")),
            _plan(("cover", "a"), ("zzz", "b"), ("chart", "c")),
        ]
    )
    out = await _run(_uc(planner, FakeWriter()))
    assert planner.feedbacks[1] and "nope" in planner.feedbacks[1][0]
    assert out.slide_count == 2
    assert any("zzz" in w for w in out.warnings)


@pytest.mark.asyncio
async def test_max_slides_and_instruction_passed_to_planner():
    planner = FakePlanner([_plan(*[("chart", f"s{i}") for i in range(5)])])
    out = await _run(
        _uc(planner, FakeWriter()), cfg=_cfg(max_slides=3), instruction="3장"
    )
    assert out.slide_count == 3 and any("max_slides" in w for w in out.warnings)


@pytest.mark.asyncio
async def test_writer_failure_and_slot_violation_are_degraded():
    planner = FakePlanner([_plan(("cover", "a"), ("chart", "b"))])
    out = await _run(_uc(planner, FakeWriter(fail_index=1, long_notes=True)))
    assert out.slide_count == 2  # 실패 슬라이드도 빈 슬롯으로 렌더
    assert any("slide 1" in w and "writer" in w for w in out.warnings)
    assert any("notes" in w and "max_chars" in w for w in out.warnings)


@pytest.mark.asyncio
async def test_empty_plan_raises():
    with pytest.raises(PresentationGenerateError):
        await _run(_uc(FakePlanner([_plan(), _plan(("nope", "x"))]), FakeWriter()))


@pytest.mark.asyncio
async def test_pdf_output_converts_and_stores_pdf():
    planner = FakePlanner([_plan(("cover", "a"))])
    store, conv = FakeStore(), FakeConverter()
    out = await _run(
        _uc(planner, FakeWriter(), store, conv),
        cfg=_cfg(output_format="pdf", mcp_pptx_to_pdf_tool_id="mcp_x"),
    )
    assert conv.calls == ["mcp_x"] and out.pdf_file_id == "f2"
    assert store.saved[1][0] == "리스크보고.pdf" and store.saved[1][1] == b"%PDF-fake"


@pytest.mark.asyncio
async def test_pdf_failure_or_missing_tool_is_degraded_to_pptx():
    planner = FakePlanner([_plan(("cover", "a")), _plan(("cover", "a"))])
    out = await _run(
        _uc(planner, FakeWriter(), converter=FakeConverter(fail=True)),
        cfg=_cfg(output_format="pdf", mcp_pptx_to_pdf_tool_id="mcp_x"),
    )
    assert out.pdf_file_id is None and any("PDF" in w for w in out.warnings)
    out = await _run(
        _uc(planner, FakeWriter(), converter=None), cfg=_cfg(output_format="pdf")
    )
    assert out.pdf_file_id is None and any("PDF" in w for w in out.warnings)


@pytest.mark.asyncio
async def test_evidence_is_truncated_for_llm():
    planner = FakePlanner([_plan(("cover", "a"))])
    seen = {}

    class SpyWriter(FakeWriter):
        async def write(
            self, blueprint, pattern, plan, evidence, conversation, index, total
        ):
            seen["evidence"] = evidence
            return await super().write(
                blueprint, pattern, plan, evidence, conversation, index, total
            )

    await _run(_uc(planner, SpyWriter()), evidence="x" * 500)
    assert len(seen["evidence"]) == 50


@pytest.mark.asyncio
async def test_invalid_chart_shape_from_llm_is_degraded_not_fatal():
    """Act-1 G1: 시리즈 길이 불일치(VO ValueError)는 슬롯 제외 + warning — 덱 유지."""

    class BadChartWriter(FakeWriter):
        async def write(
            self, blueprint, pattern, plan, evidence, conversation, index, total
        ):
            slots = [
                {
                    "slot_id": "title",
                    "text": plan.title,
                    "bullets": None,
                    "table": None,
                    "chart": None,
                },
            ]
            if pattern.id == "chart":
                slots.append(
                    {
                        "slot_id": "chart",
                        "text": None,
                        "bullets": None,
                        "table": None,
                        "chart": {
                            "type": "bar",
                            "categories": ["1Q", "2Q"],
                            "series": [{"name": "r", "values": [1.0]}],
                            "unit": None,
                        },
                    }
                )
            return SlideContentDraft(slots=slots)

    planner = FakePlanner([_plan(("cover", "a"), ("chart", "b"))])
    out = await _run(_uc(planner, BadChartWriter()))
    assert out.slide_count == 2 and out.chart_count == 0
    assert any("slide 2" in w and "chart" in w for w in out.warnings)


# ── pptx-font-fidelity FR-03/FR-04 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_heading_is_carried_from_draft_to_slot_content():
    class HeadingWriter(FakeWriter):
        async def write(self, blueprint, pattern, plan, evidence, conv, index, total):
            slots = [
                {
                    "slot_id": "title",
                    "text": plan.title,
                    "bullets": None,
                    "table": None,
                    "chart": None,
                }
            ]
            if pattern.id == "chart":
                slots.append(
                    {
                        "slot_id": "notes",
                        "text": None,
                        "bullets": ["연체율 상승"],
                        "table": None,
                        "chart": None,
                        "heading": "핵심 관찰",
                    }
                )
            return SlideContentDraft(slots=slots)

    writer = HeadingWriter()
    uc = _uc(FakePlanner([_plan(("cover", "a"), ("chart", "b"))]), writer)
    captured = []
    original = uc._renderer.render

    def spy(blueprint, slides, assets, font_mapping):
        captured.extend(slides)
        return original(blueprint, slides, assets, font_mapping)

    uc._renderer.render = spy
    await _run(uc)
    notes = next(c for s in captured for c in s.slots if c.slot_id == "notes")
    assert notes.heading == "핵심 관찰"


@pytest.mark.asyncio
async def test_blank_heading_becomes_none():
    class BlankHeadingWriter(FakeWriter):
        async def write(self, blueprint, pattern, plan, evidence, conv, index, total):
            return SlideContentDraft(
                slots=[
                    {
                        "slot_id": "title",
                        "text": plan.title,
                        "bullets": None,
                        "table": None,
                        "chart": None,
                    },
                    {
                        "slot_id": "notes",
                        "text": None,
                        "bullets": ["a"],
                        "table": None,
                        "chart": None,
                        "heading": "   ",
                    },
                ]
                if pattern.id == "chart"
                else [
                    {
                        "slot_id": "title",
                        "text": plan.title,
                        "bullets": None,
                        "table": None,
                        "chart": None,
                    }
                ]
            )

    uc = _uc(FakePlanner([_plan(("chart", "b"))]), BlankHeadingWriter())
    captured = []
    original = uc._renderer.render

    def spy(blueprint, slides, assets, font_mapping):
        captured.extend(slides)
        return original(blueprint, slides, assets, font_mapping)

    uc._renderer.render = spy
    await _run(uc)
    notes = next(c for s in captured for c in s.slots if c.slot_id == "notes")
    assert notes.heading is None


@pytest.mark.asyncio
async def test_slide_without_any_renderable_content_is_skipped_with_warning():
    """FR-04: 내용이 전무한 슬라이드는 렌더에서 제외하고 사유를 남긴다."""

    class EmptyWriter(FakeWriter):
        async def write(self, blueprint, pattern, plan, evidence, conv, index, total):
            if pattern.id == "chart":
                return SlideContentDraft(slots=[])
            return SlideContentDraft(
                slots=[
                    {
                        "slot_id": "title",
                        "text": plan.title,
                        "bullets": None,
                        "table": None,
                        "chart": None,
                    }
                ]
            )

    # 제목 폴백(FR-04)도 못 쓰는 상태 — plan.title 까지 비어 있어야 진짜 빈 슬라이드
    planner = FakePlanner([_plan(("cover", "a"), ("chart", ""))])
    out = await _run(_uc(planner, EmptyWriter()))
    assert out.slide_count == 1
    assert any("slide 2" in w and "내용 없음" in w for w in out.warnings)


@pytest.mark.asyncio
async def test_slide_with_only_plan_title_is_kept_for_header_fallback():
    """FR-04: 슬롯 내용이 없어도 계획 제목이 있으면 헤더를 그리므로 남긴다."""

    class NoSlotWriter(FakeWriter):
        async def write(self, blueprint, pattern, plan, evidence, conv, index, total):
            return SlideContentDraft(slots=[])

    planner = FakePlanner([_plan(("chart", "2. 연체율 추이"))])
    out = await _run(_uc(planner, NoSlotWriter()))
    assert out.slide_count == 1
    assert not any("내용 없음" in w for w in out.warnings)


# ── blueprint-slot-content-fill §8.3 시나리오 32~34 — 목차 결정론 결선 ──────

from dataclasses import replace as _replace  # noqa: E402


def _bp_with_toc() -> DocumentBlueprint:
    bp = _bp()
    toc = PagePattern(
        "toc",
        PatternKind.TOC,
        (
            Slot("title", SlotKind.TITLE, RelBox(0.05, 0.05, 0.9, 0.1), "제목",
                 40, None, None),
            Slot("bullets", SlotKind.BULLETS, RelBox(0.1, 0.2, 0.8, 0.6), "항목",
                 400, None, None),
        ),
        None,
        2,
        "",
    )
    return _replace(bp, patterns=(*bp.patterns, toc))


async def _run_with_toc(uc, cfg=None):
    return await uc.generate(
        llm=MagicMock(),
        blueprint=_bp_with_toc(),
        assets={},
        tool_config=cfg or _cfg(),
        evidence_block="근거",
        conversation_block="대화",
        user_instruction="",
        owner_user_id="u1",
        request_id="r1",
    )


@pytest.mark.asyncio
async def test_toc_slide_skips_writer_and_uses_planned_titles():
    """시나리오 32 (SC-6) — 목차는 writer 를 거치지 않는다."""
    planner = FakePlanner(
        [_plan(("cover", "표지"), ("toc", "목차"), ("chart", "연체율 추이"))]
    )
    writer = FakeWriter()

    out = await _run_with_toc(_uc(planner, writer))

    assert out.slide_count == 3
    called_patterns = [c[2] for c in writer.calls]
    assert "toc" not in called_patterns  # 목차는 LLM 미경유
    assert called_patterns == ["cover", "chart"]


@pytest.mark.asyncio
async def test_non_toc_slides_still_call_writer():
    """시나리오 33 — 나머지 슬라이드는 기존 경로 유지."""
    planner = FakePlanner([_plan(("cover", "표지"), ("chart", "차트"))])
    writer = FakeWriter()

    await _run_with_toc(_uc(planner, writer))

    assert [c[2] for c in writer.calls] == ["cover", "chart"]


@pytest.mark.asyncio
async def test_toc_falls_back_to_writer_when_no_items():
    """시나리오 34 — 목차 외 슬라이드가 없으면 writer 로 폴백."""
    planner = FakePlanner([_plan(("toc", "목차"))])
    writer = FakeWriter()

    await _run_with_toc(_uc(planner, writer))

    assert [c[2] for c in writer.calls] == ["toc"]
