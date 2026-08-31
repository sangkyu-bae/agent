"""BlueprintExtractionUseCase (Design §2.2 추출 흐름 / §6.3 degraded 경계).

실 추출기(PyMuPDF/python-pptx) + fake 비전 어댑터 + fake 종합.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from src.application.blueprint.extraction_use_case import (
    BlueprintExtractionUseCase,
    VisionProviderPort,
    VisionSession,
)
from src.application.blueprint.registries import SampleExtractorRegistry
from src.domain.blueprint.errors import UnsupportedSampleFormatError
from src.domain.blueprint.schemas import (
    NarrativeDraft,
    NarrativeSectionDraft,
    PagePatternDraft,
    SlotDraft,
)
from src.domain.blueprint.value_objects import PatternKind, SlotKind
from src.domain.multimodal.errors import MultimodalNotConfiguredError
from src.domain.multimodal.interfaces import DescribeOutcome
from src.domain.multimodal.value_objects import MultimodalSettings
from src.infrastructure.blueprint.extractors.pdf_style_extractor import (
    PdfStyleExtractor,
)
from src.infrastructure.blueprint.extractors.pptx_style_extractor import (
    PptxStyleExtractor,
)
from src.infrastructure.blueprint.fonts import FontCatalog
from src.infrastructure.blueprint.llm.synthesizer import NarrativeSynthesizer
from src.infrastructure.blueprint.vision.page_classifier import VisionPageClassifier

from tests.fixtures.blueprint_samples import sample_pdf, sample_pptx

KINDS = ["cover", "toc", "chart_with_notes", "table", "closing"]


def _pattern_draft(kind: str) -> PagePatternDraft:
    slots = [
        SlotDraft(kind="title", x=0.08, y=0.1, w=0.8, h=0.12, role="제목", max_chars=40)
    ]
    if kind == "chart_with_notes":
        slots.append(
            SlotDraft(
                kind="chart", x=0.08, y=0.25, w=0.45, h=0.5, role="차트", max_chars=None
            )
        )
        slots.append(
            SlotDraft(
                kind="text", x=0.58, y=0.3, w=0.35, h=0.4, role="해설", max_chars=200
            )
        )
    elif kind == "table":
        slots.append(
            SlotDraft(
                kind="table", x=0.08, y=0.25, w=0.84, h=0.55, role="표", max_chars=None
            )
        )
    elif kind != "cover":
        slots.append(
            SlotDraft(
                kind="bullets", x=0.1, y=0.3, w=0.8, h=0.5, role="본문", max_chars=300
            )
        )
    return PagePatternDraft(kind=kind, slots=slots, layout_notes=f"{kind} page")


class FakeAdapter:
    """describe_with 만 쓰는 VisionDescriberPort 흉내 (스키마별 응답)."""

    provider = "fake"

    def __init__(self, fail_pages: set[int] = frozenset(), narrative_fail=False):
        self.calls = 0
        self.fail_pages = set(fail_pages)
        self.narrative_fail = narrative_fail
        self.messages: list = []

    def build_image_block(self, image, options):
        return {"type": "image", "page": image.page, "bytes": len(image.image_bytes)}

    async def describe_with(self, messages, schema):
        await asyncio.sleep(0)
        self.messages.append(messages)
        if schema is NarrativeDraft:
            if self.narrative_fail:
                raise ValueError("narrative boom")
            return DescribeOutcome(
                draft=NarrativeDraft(
                    sections=[
                        NarrativeSectionDraft(
                            role="표지", pattern_ids=["p1"], guidance="주제·부서"
                        )
                    ],
                    tone="보고체",
                    language="ko",
                ),
                degraded_output_mode=False,
                output_mode="strict",
                usage={"total_tokens": 5},
            )
        page = _page_of(messages)
        self.calls += 1
        if page in self.fail_pages:
            raise TimeoutError("slow vision")
        return DescribeOutcome(
            draft=_pattern_draft(KINDS[page - 1]),
            degraded_output_mode=False,
            output_mode="strict",
            usage={"total_tokens": 10},
        )


def _page_of(messages) -> int:
    human = messages[-1]
    return next(
        b["page"]
        for b in human.content
        if isinstance(b, dict) and b.get("type") == "image"
    )


def _settings(**over) -> MultimodalSettings:
    base = dict(
        id="s",
        enabled=True,
        vision_model_id="m1",
        max_images_per_doc=50,
        min_image_px=100,
        min_area_ratio=0.02,
        concurrency=2,
        timeout_sec=5,
        output_language="ko",
        detail_level="brief",
        updated_at=datetime.now(UTC),
    )
    base.update(over)
    return MultimodalSettings(**base)


class FakeProvider(VisionProviderPort):
    def __init__(self, adapter, settings=None, error=None):
        self._adapter, self._settings, self._error = (
            adapter,
            settings or _settings(),
            error,
        )

    async def resolve(self, request_id: str) -> VisionSession:
        if self._error:
            raise self._error
        return VisionSession(
            settings=self._settings,
            classifier=VisionPageClassifier(self._adapter),
            synthesizer=NarrativeSynthesizer(self._adapter),
        )


def _uc(adapter, provider=None, tmp_path=None) -> BlueprintExtractionUseCase:
    reg = SampleExtractorRegistry()
    reg.register(PdfStyleExtractor(render_dpi=36))
    reg.register(PptxStyleExtractor())
    fonts = FontCatalog(font_dir=tmp_path, default="NanumGothic")
    return BlueprintExtractionUseCase(
        extractors=reg,
        vision=provider or FakeProvider(adapter),
        fonts=fonts,
        logger=MagicMock(),
    )


@pytest.mark.asyncio
async def test_pdf_full_flow_builds_blueprint_with_assets_and_thumbnails(tmp_path):
    adapter = FakeAdapter()
    out = await _uc(adapter, tmp_path=tmp_path).run(
        sample_pdf(), "sample.pdf", 60, "req-1"
    )
    bp = out.blueprint
    assert bp.source_kind == "pdf" and bp.page_count == 5 and bp.name == "sample"
    assert [p.kind.value for p in bp.patterns] == KINDS
    assert [p.id for p in bp.patterns] == ["p1", "p2", "p3", "p4", "p5"]
    assert [p.sample_page for p in bp.patterns] == [1, 2, 3, 4, 5]
    assert bp.style.palette["primary"] == "#1F3A5F" and bp.style.sizes["h1"] == 28.0
    assert sorted(a.kind for a in bp.assets) == ["cover", "logo"]
    logo = next(a for a in bp.assets if a.kind == "logo")
    assert bp.style.header_footer.logo_asset_id == logo.id
    assert out.assets[logo.id][:4] == b"\x89PNG"
    assert len(out.page_thumbnails) == 5 and all(t for t in out.page_thumbnails)
    assert out.classification == (5, 0) and adapter.calls == 5
    assert bp.narrative.sections[0].pattern_ids == ("p1",)
    assert any("not installed" in w for w in bp.warnings)  # 폰트 미설치 경고
    assert set(bp.font_mapping) >= {"Helvetica-Bold", "Helvetica"}
    assert bp.status == "active" and bp.id


@pytest.mark.asyncio
async def test_vision_failure_on_one_page_is_degraded_unknown(tmp_path):
    adapter = FakeAdapter(fail_pages={3})
    out = await _uc(adapter, tmp_path=tmp_path).run(sample_pdf(), "s.pdf", 60, "r")
    kinds = [p.kind for p in out.blueprint.patterns]
    assert kinds[2] is PatternKind.UNKNOWN and kinds[0] is PatternKind.COVER
    assert out.classification == (4, 1)
    assert any("page 3" in w for w in out.blueprint.warnings)
    unknown = out.blueprint.patterns[2]
    assert {s.kind for s in unknown.slots} >= {SlotKind.TITLE, SlotKind.TEXT}


@pytest.mark.asyncio
async def test_narrative_failure_falls_back_to_pattern_order(tmp_path):
    out = await _uc(FakeAdapter(narrative_fail=True), tmp_path=tmp_path).run(
        sample_pdf(), "s.pdf", 60, "r"
    )
    sections = out.blueprint.narrative.sections
    assert [s.pattern_ids for s in sections] == [
        ("p1",),
        ("p2",),
        ("p3",),
        ("p4",),
        ("p5",),
    ]
    assert any("narrative" in w for w in out.blueprint.warnings)


@pytest.mark.asyncio
async def test_pptx_uses_heuristic_patterns_without_vision(tmp_path):
    adapter = FakeAdapter()
    out = await _uc(adapter, tmp_path=tmp_path).run(sample_pptx(), "deck.pptx", 60, "r")
    assert adapter.calls == 0  # D4: 렌더 없음 → 비전 분류 호출 없음
    kinds = [p.kind for p in out.blueprint.patterns]
    assert kinds[0] is PatternKind.COVER
    assert kinds[2] is PatternKind.CHART_WITH_NOTES and kinds[3] is PatternKind.TABLE
    assert out.page_thumbnails == (None,) * 5
    assert out.blueprint.style.fonts == {"heading": "HeadFont", "body": "BodyFont"}


@pytest.mark.asyncio
async def test_unsupported_extension_checked_before_vision(tmp_path):
    provider = FakeProvider(FakeAdapter(), error=MultimodalNotConfiguredError("x"))
    with pytest.raises(UnsupportedSampleFormatError):
        await _uc(None, provider, tmp_path).run(b"x", "a.docx", 60, "r")


@pytest.mark.asyncio
async def test_vision_not_configured_propagates_for_pdf(tmp_path):
    provider = FakeProvider(
        FakeAdapter(), error=MultimodalNotConfiguredError("no model")
    )
    with pytest.raises(MultimodalNotConfiguredError):
        await _uc(None, provider, tmp_path).run(sample_pdf(), "a.pdf", 60, "r")


@pytest.mark.asyncio
async def test_max_pages_and_concurrency_respected(tmp_path):
    adapter = FakeAdapter()
    out = await _uc(
        adapter, FakeProvider(adapter, _settings(concurrency=1)), tmp_path
    ).run(sample_pdf(), "s.pdf", 2, "r")
    assert out.blueprint.page_count == 2 and adapter.calls == 2
    assert out.timings_ms["extract"] >= 0 and "classify" in out.timings_ms


@pytest.mark.asyncio
async def test_page_hints_are_sent_to_vision(tmp_path):
    adapter = FakeAdapter()
    await _uc(adapter, tmp_path=tmp_path).run(sample_pdf(), "s.pdf", 60, "r")
    # 4페이지(표) 메시지 텍스트에 표 힌트 + 제목 후보가 들어간다
    msgs = next(m for m in adapter.messages if m[-1].content and _page_of(m) == 4)
    text = " ".join(b.get("text", "") for b in msgs[-1].content if isinstance(b, dict))
    assert "tables=1" in text or "tables: 1" in text
    assert "Portfolio Summary" in text


# ── blueprint-style-fidelity §3.3 조립 — 골든 샘플 실데이터 ─────────────────

import json  # noqa: E402
from pathlib import Path  # noqa: E402

_GOLDEN_PDF = Path(__file__).parents[3] / "samples" / "golden_sample_report.pdf"
_GOLDEN_V1 = Path(__file__).parents[2] / "fixtures" / "blueprint" / "golden_v1.json"


class GoldenAdapter(FakeAdapter):
    """분류 결과를 DB 스냅샷(golden_v1.json)의 패턴으로 고정 — 비전 비결정성 제거."""

    def __init__(self):
        super().__init__()
        data = json.loads(_GOLDEN_V1.read_text(encoding="utf-8"))
        self.drafts = {
            p["sample_page"]: PagePatternDraft(
                kind=p["kind"],
                slots=[
                    SlotDraft(
                        kind=s["kind"],
                        x=s["box"]["x"],
                        y=s["box"]["y"],
                        w=s["box"]["w"],
                        h=s["box"]["h"],
                        role=s["role"],
                        max_chars=s["max_chars"],
                        align="center"
                        if s["kind"] == "title" and p["kind"] == "cover"
                        else "left",
                    )
                    for s in p["slots"]
                ],
                layout_notes=p["notes"],
            )
            for p in data["patterns"]
        }

    async def describe_with(self, messages, schema):
        if schema is NarrativeDraft:
            return await super().describe_with(messages, schema)
        await asyncio.sleep(0)
        self.calls += 1
        return DescribeOutcome(
            draft=self.drafts[_page_of(messages)],
            degraded_output_mode=False,
            output_mode="strict",
            usage={"total_tokens": 10},
        )


@pytest.mark.asyncio
async def test_golden_sample_assembly_preserves_style_information(tmp_path):
    out = await _uc(GoldenAdapter(), tmp_path=tmp_path).run(
        _GOLDEN_PDF.read_bytes(), "golden_sample_report.pdf", 20, "req-g"
    )
    bp, style = out.blueprint, out.blueprint.style
    assert bp.schema_version == 2
    # SC-1 폰트 정규화 (pptx-font-fidelity FR-01) — 서브패밀리 접미사 제거
    assert bp.font_mapping["Malgun Gothic Bold"] == "Malgun Gothic"
    assert bp.font_mapping["Malgun Gothic Regular"] == "Malgun Gothic"
    # SC-2 로고 = 본문 좌표, cover_box = 표지 좌표
    logo = next(a for a in bp.assets if a.kind == "logo")
    assert logo.box.x == pytest.approx(0.83, abs=0.02) and logo.box.y < 0.1
    assert logo.cover_box is not None and logo.cover_box.x == pytest.approx(
        0.06, abs=0.02
    )
    # SC-4 푸터 텍스트·좌표
    hf = style.header_footer
    assert hf.footer_text == "여신심사부 · 대외비 · 2026년 3분기"
    assert hf.page_number_format == "{n} / {total}"
    assert hf.footer_box is not None and hf.page_number_box is not None
    assert hf.page_number_box.x > 0.85 and hf.footer_color == "#666666"
    assert hf.logo_asset_id == logo.id
    # SC-5 푸터 띠 공통 장식 + p3/p6 카드
    assert any(d.fill == "#F3F4F6" and d.box.y > 0.9 for d in style.common_decorations)
    assert len(bp.pattern("p6").decorations) == 6  # 카드 3 + 악센트 줄무늬 3
    assert len(bp.pattern("p3").decorations) == 2  # 카드 + 줄무늬
    assert bp.pattern("p5").decorations == ()  # 표 내부 채움은 장식 아님
    assert bp.pattern("p4").decorations == ()  # 차트 막대는 장식 아님
    # SC-6 크기 계층 / SC-7 팔레트
    assert style.sizes["h1"] == 34 and style.sizes["h2"] == 24
    assert style.sizes["subtitle"] == 18 and style.sizes["h3"] == 16
    assert (
        style.palette["primary"] == "#1F3A5F" and style.palette["accent1"] == "#E07A1F"
    )
    # align 전달
    assert bp.pattern("p1").slot("title").align == "center"
    assert bp.pattern("p2").slot("title").align == "left"


def test_pattern_from_draft_trusts_align_only_for_cover_title():
    """G7 (Plan §5 위험 완화): align 은 표지 title 만 LLM 값 신뢰, 나머지는 left."""
    from src.application.blueprint.extraction_use_case import _pattern_from_draft

    def draft(kind):
        return PagePatternDraft(
            kind=kind,
            slots=[
                SlotDraft(
                    kind="title", x=0.1, y=0.1, w=0.8, h=0.1, role="t", align="center"
                ),
                SlotDraft(
                    kind="text", x=0.1, y=0.3, w=0.8, h=0.1, role="b", align="right"
                ),
            ],
            layout_notes="",
        )

    cover = _pattern_from_draft(draft("cover"), 1)
    assert cover.slot("title").align == "center" and cover.slot("text").align == "left"
    body = _pattern_from_draft(draft("text"), 2)
    assert body.slot("title").align == "left" and body.slot("text").align == "left"


# ── blueprint-slot-box-snap §8.3 시나리오 20~23 — 결선 ──────────────────────


@pytest.mark.asyncio
async def test_extraction_snaps_text_slot_boxes(tmp_path):
    """시나리오 20 — 추출 결과의 텍스트 슬롯이 실측 좌표를 갖는다."""
    from tests.integration.blueprint.test_golden_sample_fidelity import _PDF

    out = await _uc(GoldenAdapter(), tmp_path=tmp_path).run(
        _PDF.read_bytes(), "golden.pdf", 20, "snap-1"
    )

    texty = {"title", "text", "bullets"}
    boxes = [
        s.box for p in out.blueprint.patterns for s in p.slots if s.kind.value in texty
    ]
    assert boxes, "텍스트 슬롯 없음"
    # 비전 추정값은 0.05 배수 — 하나도 남아 있으면 스냅이 안 된 것
    estimates = [b for b in boxes if _is_grid(b.x) and _is_grid(b.y)]
    assert estimates == [], estimates


def _is_grid(v: float) -> bool:
    return abs(v * 20 - round(v * 20)) < 1e-9


@pytest.mark.asyncio
async def test_snap_runs_after_decoration_policy(tmp_path):
    """시나리오 21·22 — 장식이 먼저 확정되고, 장식 판정은 스냅에 영향받지 않는다."""
    from tests.integration.blueprint.test_golden_sample_fidelity import _PDF

    out = await _uc(GoldenAdapter(), tmp_path=tmp_path).run(
        _PDF.read_bytes(), "golden.pdf", 20, "snap-2"
    )
    bp = out.blueprint

    p3 = next(p for p in bp.patterns if p.id == "p3")
    assert p3.decorations, "장식이 스냅 이후에도 유지돼야 한다"
    # 장식은 실측 좌표 그대로 (스냅 대상 아님)
    assert any(abs(d.box.y - 0.222) < 0.01 for d in p3.decorations), [
        d.box for d in p3.decorations
    ]


@pytest.mark.asyncio
async def test_snap_warnings_are_collected_into_blueprint(tmp_path):
    """시나리오 23 — 스냅 경고가 blueprint.warnings 로 전파되는 경로가 살아 있다."""
    from tests.integration.blueprint.test_golden_sample_fidelity import _PDF

    out = await _uc(GoldenAdapter(), tmp_path=tmp_path).run(
        _PDF.read_bytes(), "golden.pdf", 20, "snap-3"
    )

    # 골든 샘플은 전 슬롯이 매칭되므로 스냅 경고가 없어야 한다
    assert [w for w in out.blueprint.warnings if "매칭 span 없음" in w] == []


# ── blueprint-slot-content-fill §8.3 시나리오 30 — 장식 판정 불변 ────────────


@pytest.mark.asyncio
async def test_decoration_output_is_unaffected_by_slot_split(tmp_path):
    """설계 §2.3 — 분할은 텍스트 슬롯만 건드리므로 DecorationPolicy 출력이 같다.

    _CONTENT_SLOT_KINDS 에 텍스트 종류가 추가되면 이 단언이 깨져 알려 준다.
    """
    from src.domain.blueprint.policies import DecorationPolicy, PaletteClusterPolicy
    from src.infrastructure.blueprint.extractors.pdf_style_extractor import (
        PdfStyleExtractor,
    )

    from tests.integration.blueprint.test_golden_sample_fidelity import _PDF

    out = await _uc(GoldenAdapter(), tmp_path=tmp_path).run(
        _PDF.read_bytes(), "golden.pdf", 20, "deco-invariance"
    )
    bp = out.blueprint
    stats = PdfStyleExtractor(render_dpi=36).extract(_PDF.read_bytes(), "g.pdf", 20)
    palette = PaletteClusterPolicy.apply(stats)

    # 분할된(=최종) 패턴으로 장식을 다시 계산해도 저장된 장식과 동일해야 한다
    common, per_pattern, _ = DecorationPolicy.apply(stats, bp.patterns, palette)

    assert common == bp.style.common_decorations
    for pattern in bp.patterns:
        assert per_pattern.get(pattern.id, ()) == pattern.decorations


# ── blueprint-render-style-fidelity §5.1 — 추출 기본값이 스타일을 켠다 ───────


@pytest.mark.asyncio
async def test_extraction_enables_render_style_with_golden_defaults(tmp_path):
    """DR-10(v2) — 신규 추출은 골든 실측값을 넣어 기본 산출물이 원본을 닮는다.

    VO 기본값(꺼짐)은 하위호환용이고, 추출은 켠 값을 쓴다.
    """
    from tests.integration.blueprint.test_golden_sample_fidelity import _PDF

    out = await _uc(GoldenAdapter(), tmp_path=tmp_path).run(
        _PDF.read_bytes(), "golden.pdf", 20, "style-defaults"
    )
    style = out.blueprint.style

    assert style.table_style.zebra is True
    assert style.table_style.border_width_pt == 0.75
    assert style.body_line_spacing == 1.45
    assert style.body_space_after_pt == 33.2
    assert style.chart_label_size_pt == style.sizes["caption"]
