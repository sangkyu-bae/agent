"""domain/blueprint VO 검증 (Design §3.1, D1 좌표 0..1 비율)."""

from datetime import UTC, datetime

import pytest
from src.domain.blueprint.value_objects import (
    BlueprintAsset,
    ChartSpec,
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
    TableSpec,
    TableStyle,
)


def _box(**over) -> RelBox:
    base = dict(x=0.1, y=0.1, w=0.5, h=0.2)
    base.update(over)
    return RelBox(**base)


def _slot(id="title", kind=SlotKind.TITLE, **over) -> Slot:
    base = dict(
        id=id,
        kind=kind,
        box=_box(),
        role="제목",
        max_chars=40,
        max_rows=None,
        asset_id=None,
    )
    base.update(over)
    return Slot(**base)


def _pattern(id="p1", kind=PatternKind.COVER, slots=None) -> PagePattern:
    return PagePattern(
        id=id,
        kind=kind,
        slots=tuple(slots or (_slot(),)),
        background="#1F3A5F",
        sample_page=1,
        notes="",
    )


def _style() -> StyleTokens:
    return StyleTokens(
        slide_size=(13.333, 7.5),
        fonts={"heading": "HY헤드라인M", "body": "맑은 고딕"},
        sizes={"h1": 28.0, "h2": 20.0, "body": 14.0, "caption": 10.0},
        palette={
            "primary": "#1F3A5F",
            "accent1": "#E07A1F",
            "text": "#222222",
            "bg": "#FFFFFF",
        },
        table_style=TableStyle(
            header_bg="#1F3A5F", header_text="#FFFFFF", border="#CCCCCC", zebra=True
        ),
        header_footer=HeaderFooter(
            logo_asset_id=None, page_number_format="{n} / {total}", footer_text=""
        ),
    )


def _blueprint(**over) -> DocumentBlueprint:
    now = datetime.now(UTC)
    base = dict(
        id="b1",
        name="샘플",
        description="",
        schema_version=1,
        source_kind="pdf",
        page_count=5,
        style=_style(),
        patterns=(_pattern(),),
        narrative=Narrative(
            sections=(NarrativeSection(role="표지", pattern_ids=("p1",), guidance=""),),
            tone="보고체",
            language="ko",
        ),
        assets=(),
        font_mapping={"HY헤드라인M": "NanumGothicBold"},
        warnings=(),
        status="active",
        created_at=now,
        updated_at=now,
    )
    base.update(over)
    return DocumentBlueprint(**base)


# ── RelBox ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "bad", [dict(x=-0.01), dict(w=0.0), dict(x=0.6, w=0.5), dict(h=1.1)]
)
def test_relbox_rejects_out_of_range(bad):
    with pytest.raises(ValueError):
        _box(**bad)


def test_relbox_edge_exactly_one_is_allowed():
    _box(x=0.5, w=0.5, y=0.0, h=1.0)


# ── Slot / PagePattern ───────────────────────────────────────────────────────


def test_slot_requires_id_and_positive_limits():
    with pytest.raises(ValueError):
        _slot(id="")
    with pytest.raises(ValueError):
        _slot(max_chars=0)


def test_pattern_rejects_duplicate_slot_ids_and_empty_slots():
    with pytest.raises(ValueError):
        _pattern(slots=(_slot("a"), _slot("a")))
    with pytest.raises(ValueError):
        PagePattern(
            id="p",
            kind=PatternKind.TEXT,
            slots=(),
            background=None,
            sample_page=1,
            notes="",
        )


def test_pattern_kinds_cover_design_list():
    assert {k.value for k in PatternKind} == {
        "cover",
        "toc",
        "section_lead",
        "text",
        "chart_with_notes",
        "table",
        "two_column",
        "image_with_notes",
        "closing",
        "unknown",
    }
    assert {k.value for k in SlotKind} == {
        "title",
        "text",
        "bullets",
        "table",
        "chart",
        "image",
        "footer",
    }


# ── StyleTokens ──────────────────────────────────────────────────────────────


def test_style_requires_core_palette_and_sizes():
    s = _style()
    with pytest.raises(ValueError):
        StyleTokens(**{**s.__dict__, "palette": {"primary": "#000000"}})
    with pytest.raises(ValueError):
        StyleTokens(**{**s.__dict__, "sizes": {"h1": 28.0}})


def test_style_rejects_non_hex_color_and_bad_slide_size():
    s = _style()
    with pytest.raises(ValueError):
        StyleTokens(**{**s.__dict__, "palette": {**s.palette, "primary": "blue"}})
    with pytest.raises(ValueError):
        StyleTokens(**{**s.__dict__, "slide_size": (0.0, 7.5)})


# ── DocumentBlueprint ────────────────────────────────────────────────────────


def test_blueprint_rejects_duplicate_pattern_ids():
    with pytest.raises(ValueError):
        _blueprint(patterns=(_pattern("p1"), _pattern("p1")))


def test_blueprint_rejects_narrative_referencing_unknown_pattern():
    with pytest.raises(ValueError):
        _blueprint(
            narrative=Narrative(
                sections=(
                    NarrativeSection(role="x", pattern_ids=("nope",), guidance=""),
                ),
                tone="",
                language="ko",
            )
        )


def test_blueprint_rejects_invalid_source_kind_status_and_name():
    with pytest.raises(ValueError):
        _blueprint(source_kind="docx")
    with pytest.raises(ValueError):
        _blueprint(status="deleted")
    with pytest.raises(ValueError):
        _blueprint(name="")


def test_blueprint_pattern_lookup_and_active_assets():
    asset = BlueprintAsset(
        id="a1",
        kind="logo",
        mime="image/png",
        width=10,
        height=10,
        sha256="0" * 64,
        box=_box(),
        adopted=False,
    )
    bp = _blueprint(assets=(asset,))
    assert bp.pattern("p1").kind is PatternKind.COVER
    assert bp.pattern("zzz") is None
    assert bp.adopted_assets() == ()


def test_image_slot_asset_must_exist_in_blueprint():
    slot = _slot("logo", SlotKind.IMAGE, asset_id="missing")
    with pytest.raises(ValueError):
        _blueprint(patterns=(_pattern(slots=(_slot(), slot)),))


# ── 생성 측 VO ───────────────────────────────────────────────────────────────


def test_chart_spec_requires_equal_lengths_and_known_type():
    ChartSpec(
        type="bar", categories=("1Q", "2Q"), series=(("a", (1.0, 2.0)),), unit=None
    )
    with pytest.raises(ValueError):
        ChartSpec(
            type="bar", categories=("1Q",), series=(("a", (1.0, 2.0)),), unit=None
        )
    with pytest.raises(ValueError):
        ChartSpec(
            type="scatter", categories=("1Q",), series=(("a", (1.0,)),), unit=None
        )
    with pytest.raises(ValueError):
        ChartSpec(type="pie", categories=("1Q",), series=(), unit=None)


def test_table_spec_rows_match_header_width():
    TableSpec(header=("a", "b"), rows=(("1", "2"),))
    with pytest.raises(ValueError):
        TableSpec(header=("a", "b"), rows=(("1",),))
    with pytest.raises(ValueError):
        TableSpec(header=(), rows=())


def test_slide_plan_requires_positive_index_and_pattern():
    SlidePlan(index=1, pattern_id="p1", title="t", intent="", data_hint="")
    with pytest.raises(ValueError):
        SlidePlan(index=0, pattern_id="p1", title="t", intent="", data_hint="")
    with pytest.raises(ValueError):
        SlidePlan(index=1, pattern_id="", title="t", intent="", data_hint="")


# ── blueprint-style-fidelity §3.1 — schema v2 VO ────────────────────────────


def test_decoration_requires_id_and_hex():
    from src.domain.blueprint.value_objects import Decoration

    d = Decoration("deco1", "rect", RelBox(0, 0.93, 1, 0.07), "#F2F4F5")
    assert d.line is None
    with pytest.raises(ValueError):
        Decoration("", "rect", RelBox(0, 0, 1, 1), "#F2F4F5")
    with pytest.raises(ValueError):
        Decoration("d", "rect", RelBox(0, 0, 1, 1), "grey")
    with pytest.raises(ValueError):
        Decoration("d", "rect", RelBox(0, 0, 1, 1), "#F2F4F5", line="red")
    with pytest.raises(ValueError):
        Decoration("d", "circle", RelBox(0, 0, 1, 1), "#F2F4F5")


def test_slot_align_default_and_validation():
    s = Slot("t", SlotKind.TITLE, RelBox(0, 0, 1, 0.1), "r", None, None, None)
    assert s.align == "left"
    with pytest.raises(ValueError):
        Slot("t", SlotKind.TITLE, RelBox(0, 0, 1, 0.1), "r", None, None, None, "mid")


def test_pattern_decorations_default_and_duplicate_ids():
    from src.domain.blueprint.value_objects import Decoration

    slot = Slot("t", SlotKind.TITLE, RelBox(0, 0, 1, 0.1), "r", None, None, None)
    p = PagePattern("p1", PatternKind.TEXT, (slot,), None, 1, "")
    assert p.decorations == ()
    deco = Decoration("deco1", "rect", RelBox(0, 0, 1, 0.1), "#F2F4F5")
    with pytest.raises(ValueError):
        PagePattern("p1", PatternKind.TEXT, (slot,), None, 1, "", (deco, deco))


def test_header_footer_and_asset_optional_fields_default_none():
    hf = HeaderFooter(None, "{n}", "")
    assert hf.footer_box is None and hf.page_number_box is None
    assert hf.footer_color is None
    with pytest.raises(ValueError):
        HeaderFooter(None, "{n}", "", footer_color="grey")
    asset = BlueprintAsset(
        "a", "logo", "image/png", 1, 1, "f" * 64, RelBox(0, 0, 0.1, 0.1), True
    )
    assert asset.cover_box is None


def test_style_tokens_size_role_fallbacks():
    from src.domain.blueprint.value_objects import CURRENT_SCHEMA_VERSION

    assert CURRENT_SCHEMA_VERSION == 2
    base = _style()
    assert base.common_decorations == ()
    assert base.size("h1") == base.sizes["h1"]
    # h3 폴백: h2*0.65, subtitle 폴백: h1*0.55
    assert base.size("h3") == pytest.approx(base.sizes["h2"] * 0.65)
    assert base.size("subtitle") == pytest.approx(base.sizes["h1"] * 0.55)
    with_h3 = StyleTokens(
        base.slide_size,
        base.fonts,
        {**base.sizes, "h3": 16.0, "subtitle": 18.0},
        base.palette,
        base.table_style,
        base.header_footer,
    )
    assert with_h3.size("h3") == 16.0 and with_h3.size("subtitle") == 18.0
    with pytest.raises(KeyError):
        base.size("h9")
