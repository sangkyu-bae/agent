"""정책 5종 (Design §2.2 추출 흐름 / §6.3 degraded 경계)."""

from src.domain.blueprint.policies import (
    PaletteClusterPolicy,
    RepeatAssetPolicy,
    SizeHierarchyPolicy,
    SlidePlanValidationPolicy,
    SlotContentPolicy,
)
from src.domain.blueprint.value_objects import (
    ChartSpec,
    ImageRef,
    PagePattern,
    PageStats,
    PatternKind,
    RelBox,
    SampleStats,
    SlidePlan,
    Slot,
    SlotContent,
    SlotKind,
    TableSpec,
    TextSpan,
)


def _span(text, size, font="Body", bold=False, color="#222222", y=0.5, w=0.5):
    return TextSpan(
        text=text,
        font=font,
        size=size,
        bold=bold,
        color=color,
        box=RelBox(x=0.1, y=y, w=w, h=0.05),
    )


def _img(sha, x=0.85, y=0.02, w=0.1, h=0.05, data=b"\x89PNG"):
    return ImageRef(
        sha256=sha,
        mime="image/png",
        width=100,
        height=50,
        box=RelBox(x=x, y=y, w=w, h=h),
        data=data,
    )


def _page(n, spans=(), images=(), tables=(), has_text=True):
    return PageStats(
        number=n,
        width=960.0,
        height=540.0,
        spans=tuple(spans),
        images=tuple(images),
        tables=tuple(tables),
        has_text=has_text,
    )


def _stats(pages) -> SampleStats:
    return SampleStats(
        source_kind="pdf", page_size=(13.333, 7.5), pages=tuple(pages), theme_fonts={}
    )


# ── PaletteClusterPolicy ─────────────────────────────────────────────────────


def test_palette_picks_dominant_non_text_colors_and_text_color():
    spans = [
        _span("본문", 14, color="#222222"),
        _span("본문2", 14, color="#222222"),
        _span("제목", 28, color="#1F3A5F", bold=True),
        _span("강조", 14, color="#E07A1F"),
        _span("거의 같은 남색", 14, color="#1F3A60"),  # 근접색 → primary 로 병합
    ]
    p = PaletteClusterPolicy.apply(
        _stats([_page(1, spans), _page(2, [_span("x", 14, color="#1F3A5F")])])
    )
    assert p["text"] == "#222222"
    assert p["primary"] == "#1F3A5F"
    assert p["accent1"] == "#E07A1F"
    assert p["bg"] == "#FFFFFF"


def test_palette_falls_back_when_only_one_color():
    p = PaletteClusterPolicy.apply(_stats([_page(1, [_span("x", 14)])]))
    assert set(p) >= {"primary", "accent1", "text", "bg"}
    assert all(v.startswith("#") and len(v) == 7 for v in p.values())


# ── SizeHierarchyPolicy ──────────────────────────────────────────────────────


def test_size_hierarchy_infers_h1_h2_body_caption_and_fonts():
    spans = [
        _span("제목", 28, font="Head", bold=True),
        _span("부제", 20, font="Head", bold=True),
        *[_span(f"본문{i}", 14, font="Body") for i in range(10)],
        _span("캡션", 10, font="Body"),
    ]
    out = SizeHierarchyPolicy.apply(_stats([_page(1, spans)]))
    assert out.sizes == {"h1": 28.0, "h2": 20.0, "body": 14.0, "caption": 10.0}
    assert out.fonts == {"heading": "Head", "body": "Body"}


def test_size_hierarchy_with_single_size_still_returns_all_keys():
    out = SizeHierarchyPolicy.apply(_stats([_page(1, [_span("x", 12, font="F")])]))
    assert set(out.sizes) == {"h1", "h2", "body", "caption"}
    assert out.sizes["body"] == 12.0 and out.sizes["h1"] > out.sizes["body"]
    assert out.fonts == {"heading": "F", "body": "F"}


# ── RepeatAssetPolicy ────────────────────────────────────────────────────────


def test_repeat_asset_classifies_logo_decoration_cover_and_ignores_one_off():
    logo = _img("L" * 64)  # 2페이지 이상 동일 위치 → logo (작고 상단)
    deco = _img("D" * 64, x=0.0, y=0.9, w=1.0, h=0.1)  # 넓은 띠 → decoration
    cover = _img("C" * 64, x=0.0, y=0.0, w=1.0, h=1.0)  # 1페이지 전면 → cover
    once = _img("O" * 64, x=0.3, y=0.3, w=0.3, h=0.3)  # 1회 → 콘텐츠 이미지, 에셋 아님
    stats = _stats(
        [
            _page(1, images=[cover, logo]),
            _page(2, images=[logo, deco, once]),
            _page(3, images=[logo, deco]),
        ]
    )
    assets = RepeatAssetPolicy.apply(stats)
    kinds = {a.sha256[0]: a.kind for a in assets}
    assert kinds == {"L": "logo", "D": "decoration", "C": "cover"}
    assert all(a.adopted for a in assets)


def test_repeat_asset_dedupes_by_sha_and_respects_limit():
    imgs = [_img(f"{i:02d}" * 32, y=0.02 + i * 0.001) for i in range(25)]
    stats = _stats([_page(1, images=imgs), _page(2, images=imgs)])
    assets = RepeatAssetPolicy.apply(stats, max_assets=20)
    assert len(assets) == 20
    assert len({a.sha256 for a in assets}) == 20


# ── SlidePlanValidationPolicy ────────────────────────────────────────────────


def _bp_patterns():
    return (
        PagePattern(
            id="p1",
            kind=PatternKind.COVER,
            slots=(
                Slot(
                    "title",
                    SlotKind.TITLE,
                    RelBox(0.1, 0.1, 0.8, 0.2),
                    "제목",
                    40,
                    None,
                    None,
                ),
            ),
            background=None,
            sample_page=1,
            notes="",
        ),
        PagePattern(
            id="p2",
            kind=PatternKind.TEXT,
            slots=(
                Slot(
                    "body",
                    SlotKind.BULLETS,
                    RelBox(0.1, 0.3, 0.8, 0.5),
                    "본문",
                    300,
                    None,
                    None,
                ),
            ),
            background=None,
            sample_page=2,
            notes="",
        ),
    )


def test_slide_plan_validation_drops_unknown_pattern_and_enforces_max():
    plans = [
        SlidePlan(1, "p1", "표지", "", ""),
        SlidePlan(2, "zzz", "없는 패턴", "", ""),
        SlidePlan(3, "p2", "본문", "", ""),
        SlidePlan(4, "p2", "초과", "", ""),
    ]
    out = SlidePlanValidationPolicy.apply(plans, _bp_patterns(), max_slides=2)
    assert [p.pattern_id for p in out.kept] == ["p1", "p2"]
    assert [p.index for p in out.kept] == [1, 2]  # 재번호
    assert len(out.rejected) == 2
    assert any("zzz" in r for r in out.rejected) and any(
        "max_slides" in r for r in out.rejected
    )


# ── SlotContentPolicy ────────────────────────────────────────────────────────


def test_slot_content_policy_checks_kind_match_length_rows_and_series():
    pattern = PagePattern(
        id="p",
        kind=PatternKind.CHART_WITH_NOTES,
        slots=(
            Slot(
                "title",
                SlotKind.TITLE,
                RelBox(0.1, 0.05, 0.8, 0.1),
                "제목",
                10,
                None,
                None,
            ),
            Slot(
                "chart",
                SlotKind.CHART,
                RelBox(0.1, 0.2, 0.5, 0.6),
                "차트",
                None,
                None,
                None,
            ),
            Slot(
                "tbl", SlotKind.TABLE, RelBox(0.65, 0.2, 0.3, 0.6), "표", None, 2, None
            ),
        ),
        background=None,
        sample_page=1,
        notes="",
    )
    contents = [
        SlotContent(
            "title", "아주아주아주아주 긴 제목입니다", None, None, None
        ),  # > 10자
        SlotContent(
            "chart",
            None,
            None,
            None,
            ChartSpec("bar", ("a",), tuple((f"s{i}", (1.0,)) for i in range(7)), None),
        ),  # series 7 > 6
        SlotContent(
            "tbl", None, None, TableSpec(("h",), (("1",), ("2",), ("3",))), None
        ),  # rows 3 > 2
        SlotContent("ghost", "없는 슬롯", None, None, None),
        SlotContent(
            "title", None, ("불릿",), None, None
        ),  # kind 불일치 (title 에 bullets)
    ]
    out = SlotContentPolicy.apply(contents, pattern)
    # blueprint-slot-content-fill FR-05: 길이 초과(title)는 권고 — 유지된다.
    # 나머지 4건(series/rows/없는 슬롯/kind 불일치)은 치명 — 폐기.
    assert [c.slot_id for c in out.kept] == ["title"]
    assert len(out.warnings) == 5


def test_slot_content_policy_keeps_valid_and_truncates_nothing():
    pattern = PagePattern(
        id="p",
        kind=PatternKind.TEXT,
        slots=(
            Slot(
                "body",
                SlotKind.TEXT,
                RelBox(0.1, 0.1, 0.8, 0.8),
                "본문",
                100,
                None,
                None,
            ),
        ),
        background=None,
        sample_page=1,
        notes="",
    )
    out = SlotContentPolicy.apply(
        [SlotContent("body", "짧은 본문", None, None, None)], pattern
    )
    assert len(out.kept) == 1 and out.warnings == ()


def test_palette_ignores_gray_captions_when_saturated_color_exists():
    """회색 캡션·축 라벨이 아무리 많아도 채도 있는 남색이 primary."""
    spans = [_span(f"c{i}", 9, color="#666666") for i in range(20)]
    spans += [_span("제목", 24, color="#1F3A5F", bold=True), _span("본문", 13)]
    p = PaletteClusterPolicy.apply(_stats([_page(1, spans)]))
    assert p["primary"] == "#1F3A5F"


def test_palette_uses_shape_fill_colors_for_accent_weighted_by_area():
    """텍스트엔 없는 주황 도형(차트 막대)이 accent1 — 전면 배경(≥0.9)은 제외."""
    page = PageStats(
        number=1,
        width=960.0,
        height=540.0,
        spans=(
            *[_span(f"제목{i}", 24, color="#1F3A5F", bold=True) for i in range(3)],
            _span("본문", 13),
        ),
        images=(),
        tables=(),
        has_text=True,
        fills=(("#E07A1F", 0.12), ("#1F3A5F", 0.95)),
    )
    p = PaletteClusterPolicy.apply(_stats([page]))
    assert p["primary"] == "#1F3A5F" and p["accent1"] == "#E07A1F"


# ── blueprint-style-fidelity §3.3 — 정책 확장 ───────────────────────────────

from src.domain.blueprint.policies import DecorationPolicy, FooterPolicy  # noqa: E402
from src.domain.blueprint.value_objects import FillRect  # noqa: E402


def _rect(color, x, y, w, h):
    return FillRect(color=color, box=RelBox(x=x, y=y, w=w, h=h))


def _page2(n, spans=(), images=(), tables=(), rects=(), fills=()):
    return PageStats(
        number=n,
        width=960.0,
        height=540.0,
        spans=tuple(spans),
        images=tuple(images),
        tables=tuple(tables),
        has_text=True,
        fills=tuple(fills),
        rects=tuple(rects),
    )


def _footer_spans(n, total=6):
    return [
        TextSpan(
            "여신심사부 · 대외비",
            "Body",
            10,
            False,
            "#666666",
            RelBox(0.06, 0.95, 0.3, 0.03),
        ),
        TextSpan(
            f"{n} / {total}",
            "Body",
            10,
            False,
            "#666666",
            RelBox(0.92, 0.95, 0.05, 0.03),
        ),
    ]


def test_size_hierarchy_adds_h3_and_subtitle_when_present():
    spans = [
        _span("제목", 34, bold=True),
        _span("부제", 18),
        _span("섹션", 24, bold=True),
        _span("목차1", 16),
        _span("소제목", 15, bold=True),
        *[_span(f"본문 {i} 긴 문장입니다", 13) for i in range(6)],
        _span("캡션", 9),
    ]
    h = SizeHierarchyPolicy.apply(_stats([_page(1, spans)]))
    assert h.sizes["h1"] == 34 and h.sizes["h2"] == 24 and h.sizes["body"] == 13
    assert h.sizes["subtitle"] == 18  # h1~h2 사이
    assert h.sizes["h3"] == 16  # h2~body 사이 최대


def test_size_hierarchy_omits_optional_keys_when_absent():
    h = SizeHierarchyPolicy.apply(_stats([_page(1, [_span("a", 24), _span("b", 13)])]))
    assert "h3" not in h.sizes and "subtitle" not in h.sizes


def test_palette_accent_prefers_saturated_fill_over_caption_gray():
    spans = [_span("제목", 24, color="#1F3A5F", bold=True)]
    spans += [_span(f"c{i}", 9, color="#666666") for i in range(30)]
    spans += [_span("본문", 13)]
    page = _page2(1, spans, fills=(("#E07A1F", 0.02),))
    p = PaletteClusterPolicy.apply(_stats([page]))
    assert p["primary"] == "#1F3A5F" and p["accent1"] == "#E07A1F"


def test_repeat_asset_uses_body_page_box_and_keeps_cover_box():
    logo_cover = _img("L" * 64, x=0.06, y=0.07, w=0.19, h=0.11)
    logo_body = _img("L" * 64, x=0.83, y=0.04, w=0.12, h=0.07)
    pages = [_page(1, images=[logo_cover])] + [
        _page(n, images=[logo_body]) for n in range(2, 5)
    ]
    (asset,) = RepeatAssetPolicy.apply(_stats(pages))
    assert asset.kind == "logo"
    assert asset.box == logo_body.box
    assert asset.cover_box == logo_cover.box


def test_repeat_asset_without_cover_occurrence_has_no_cover_box():
    logo = _img("L" * 64)
    (asset,) = RepeatAssetPolicy.apply(
        _stats([_page(n, images=[logo]) for n in (2, 3)])
    )
    assert asset.cover_box is None and asset.box == logo.box


def test_footer_policy_detects_repeated_text_and_page_number():
    pages = [_page(1, [_span("표지", 34)])] + [
        _page(n, _footer_spans(n)) for n in range(2, 7)
    ]
    hf = FooterPolicy.apply(_stats(pages), caption_size=10.0)
    assert hf.footer_text == "여신심사부 · 대외비"
    assert hf.footer_box == RelBox(0.06, 0.95, 0.3, 0.03)
    assert hf.page_number_format == "{n} / {total}"
    assert hf.page_number_box == RelBox(0.92, 0.95, 0.05, 0.03)
    assert hf.footer_color == "#666666"
    assert hf.logo_asset_id is None


def test_footer_policy_returns_defaults_when_nothing_repeats():
    pages = [_page(n, [_span("본문", 13)]) for n in (1, 2, 3)]
    hf = FooterPolicy.apply(_stats(pages), caption_size=9.0)
    assert hf.footer_text == "" and hf.footer_box is None
    assert hf.page_number_format == "{n} / {total}" and hf.page_number_box is None


def test_footer_policy_ignores_large_text_in_band_and_single_page_docs():
    pages = [_page(n, [_span("결론", 24, y=0.92)]) for n in (1, 2)]
    assert FooterPolicy.apply(_stats(pages), caption_size=9.0).footer_text == ""
    one = [_page(1, _footer_spans(1))]
    assert FooterPolicy.apply(_stats(one), caption_size=10.0).footer_text == ""


def _patterns_for(pages, chart_page=None, table_page=None):
    pats = []
    for p in pages:
        slots = [
            Slot(
                "title",
                SlotKind.TITLE,
                RelBox(0.05, 0.05, 0.9, 0.1),
                "t",
                30,
                None,
                None,
            )
        ]
        if p.number == chart_page:
            box = RelBox(0.05, 0.2, 0.5, 0.6)
            slots.append(Slot("chart", SlotKind.CHART, box, "c", None, None, None))
        if p.number == table_page:
            box = RelBox(0.06, 0.22, 0.88, 0.5)
            slots.append(Slot("table", SlotKind.TABLE, box, "t", None, 12, None))
        kind = PatternKind.TEXT
        pats.append(PagePattern(f"p{p.number}", kind, tuple(slots), None, p.number, ""))
    return pats


_BAND = ("#F2F4F5", 0.0, 0.93, 1.0, 0.07)
_PALETTE = {
    "primary": "#1F3A5F",
    "accent1": "#E07A1F",
    "text": "#222222",
    "bg": "#FFFFFF",
}


def test_decoration_policy_promotes_repeated_band_and_keeps_page_cards():
    pages = [
        _page2(1, rects=[_rect("#1F3A5F", 0, 0, 1, 1)]),  # 표지 전면 — 제외(면적)
        _page2(2, rects=[_rect(*_BAND)]),
        _page2(3, rects=[_rect(*_BAND), _rect("#F2F4F5", 0.06, 0.22, 0.88, 0.15)]),
        _page2(4, rects=[_rect(*_BAND)]),
    ]
    common, per_pattern, warnings = DecorationPolicy.apply(
        _stats(pages), _patterns_for(pages), _PALETTE
    )
    assert [d.fill for d in common] == ["#F2F4F5"]
    assert common[0].box == RelBox(0.0, 0.93, 1.0, 0.07) and common[0].id == "common1"
    assert per_pattern.get("p2", ()) == ()
    (card,) = per_pattern["p3"]
    assert card.box == RelBox(0.06, 0.22, 0.88, 0.15) and card.id == "deco1"
    assert "p1" not in per_pattern and warnings == []


def test_decoration_policy_excludes_chart_bars_tables_and_bg_like_fills():
    bars = [_rect("#1F3A5F", 0.12 + i * 0.1, 0.5, 0.05, 0.32) for i in range(5)]
    accent_line = _rect("#E07A1F", 0.14, 0.63, 0.41, 0.01)
    table_fill = _rect("#1F3A5F", 0.06, 0.22, 0.88, 0.08)
    white = _rect("#FEFEFE", 0.1, 0.1, 0.5, 0.3)
    page = _page2(2, rects=[*bars, accent_line, table_fill, white])
    pats = _patterns_for([page], chart_page=2, table_page=2)
    common, per_pattern, _ = DecorationPolicy.apply(_stats([page]), pats, _PALETTE)
    assert common == () and per_pattern.get("p2", ()) == ()


def test_decoration_policy_keeps_thin_accent_stripe_without_chart_slot():
    """카드 왼쪽 악센트 줄무늬(0.01 폭)는 차트가 없는 페이지에선 장식이다."""
    card = _rect("#F3F4F6", 0.06, 0.24, 0.88, 0.167)
    stripe = _rect("#E07A1F", 0.06, 0.24, 0.01, 0.167)
    page = _page2(2, rects=[card, stripe])
    _, per_pattern, _ = DecorationPolicy.apply(
        _stats([page]), _patterns_for([page]), _PALETTE
    )
    assert [d.fill for d in per_pattern["p2"]] == ["#F3F4F6", "#E07A1F"]


def test_decoration_policy_caps_count_with_warning():
    rects = [_rect("#F2F4F5", 0.05, 0.05 + i * 0.09, 0.9, 0.05) for i in range(10)]
    page = _page2(2, rects=rects)
    _, per_pattern, warnings = DecorationPolicy.apply(
        _stats([page]), _patterns_for([page]), _PALETTE
    )
    assert len(per_pattern["p2"]) == 8 and len(warnings) == 1


def test_slot_content_policy_silently_drops_footer_content():
    """DR-2: LLM 이 footer 슬롯을 채워 와도 경고 없이 버린다 (렌더러가 그림)."""
    footer = Slot(
        "footer", SlotKind.FOOTER, RelBox(0.05, 0.9, 0.9, 0.05), "f", 50, None, None
    )
    title = Slot(
        "title", SlotKind.TITLE, RelBox(0.05, 0.05, 0.9, 0.1), "t", 30, None, None
    )
    pattern = PagePattern("p1", PatternKind.TEXT, (title, footer), None, 1, "")
    out = SlotContentPolicy.apply(
        [
            SlotContent("title", "제목", None, None, None),
            SlotContent("footer", "페이지 3", None, None, None),
        ],
        pattern,
    )
    assert [c.slot_id for c in out.kept] == ["title"] and out.warnings == ()


def test_decoration_policy_common_cap_emits_warning():
    """G2: 공통 장식도 상한(4) 초과 시 경고."""
    rects = [_rect("#F3F4F6", 0.05, 0.05 + i * 0.1, 0.9, 0.05) for i in range(6)]
    pages = [_page2(n, rects=rects) for n in (2, 3)]
    common, per_pattern, warnings = DecorationPolicy.apply(
        _stats(pages), _patterns_for(pages), _PALETTE
    )
    assert len(common) == 4 and per_pattern == {}
    assert any("common" in w for w in warnings)


# ── blueprint-slot-content-fill §8.2 시나리오 21~27 — 치명/권고 분리 (FR-05) ──


def _len_pattern(kind: SlotKind, max_chars: int) -> PagePattern:
    return PagePattern(
        id="p",
        kind=PatternKind.TEXT,
        slots=(
            Slot("s", kind, RelBox(0.1, 0.1, 0.8, 0.8), "역할", max_chars, None, None),
        ),
        background=None,
        sample_page=1,
        notes="",
    )


def test_bullets_over_max_chars_is_advisory_and_kept():
    """시나리오 21 — 길이 초과 bullets 가 살아남는다."""
    pattern = _len_pattern(SlotKind.BULLETS, 10)
    content = SlotContent("s", None, ("아주 긴 불릿 내용입니다",), None, None)

    out = SlotContentPolicy.apply([content], pattern)

    assert [c.slot_id for c in out.kept] == ["s"]
    assert len(out.warnings) == 1 and "max_chars" in out.warnings[0]


def test_text_over_max_chars_is_advisory_and_kept():
    """시나리오 22 — 길이 초과 text 가 살아남는다."""
    pattern = _len_pattern(SlotKind.TEXT, 5)
    content = SlotContent("s", "열 글자가 넘는 본문입니다", None, None, None)

    out = SlotContentPolicy.apply([content], pattern)

    assert [c.slot_id for c in out.kept] == ["s"]
    assert len(out.warnings) == 1


def test_shape_mismatch_stays_fatal():
    """시나리오 23·24 — 모양 불일치는 여전히 폐기된다."""
    text_slot = _len_pattern(SlotKind.TEXT, 100)
    bullets_slot = _len_pattern(SlotKind.BULLETS, 100)

    a = SlotContentPolicy.apply([SlotContent("s", None, ("x",), None, None)], text_slot)
    b = SlotContentPolicy.apply([SlotContent("s", "x", None, None, None)], bullets_slot)

    assert a.kept == () and len(a.warnings) == 1
    assert b.kept == () and len(b.warnings) == 1


def test_table_over_max_rows_stays_fatal():
    """시나리오 25 (DR-9) — 표 행 초과는 실제 도형이 넘치므로 치명 유지."""
    pattern = PagePattern(
        id="p",
        kind=PatternKind.TABLE,
        slots=(
            Slot("t", SlotKind.TABLE, RelBox(0.1, 0.1, 0.8, 0.8), "표", None, 2, None),
        ),
        background=None,
        sample_page=1,
        notes="",
    )
    table = TableSpec(("h",), (("1",), ("2",), ("3",)))

    out = SlotContentPolicy.apply([SlotContent("t", None, None, table, None)], pattern)

    assert out.kept == () and len(out.warnings) == 1


def test_unknown_slot_id_stays_fatal():
    """시나리오 26 — 패턴에 없는 슬롯은 폐기."""
    out = SlotContentPolicy.apply(
        [SlotContent("ghost", "x", None, None, None)], _len_pattern(SlotKind.TEXT, 100)
    )
    assert out.kept == () and len(out.warnings) == 1


def test_valid_content_has_no_warning():
    """시나리오 27 — 정상 내용은 경고 0건."""
    out = SlotContentPolicy.apply(
        [SlotContent("s", "짧다", None, None, None)], _len_pattern(SlotKind.TEXT, 100)
    )
    assert len(out.kept) == 1 and out.warnings == ()


def test_advisory_ignores_non_text_slots_with_max_chars():
    """방어 분기 — 표·차트 슬롯에 max_chars 가 설정돼도 권고 대상이 아니다."""
    pattern = PagePattern(
        id="p",
        kind=PatternKind.TABLE,
        slots=(
            Slot("t", SlotKind.TABLE, RelBox(0.1, 0.1, 0.8, 0.8), "표", 5, None, None),
        ),
        background=None,
        sample_page=1,
        notes="",
    )
    table = TableSpec(("헤더가 아주 길다",), (("행 내용도 길다",),))

    out = SlotContentPolicy.apply([SlotContent("t", None, None, table, None)], pattern)

    assert len(out.kept) == 1 and out.warnings == ()
