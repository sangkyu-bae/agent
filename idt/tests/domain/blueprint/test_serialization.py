"""blueprint ⇄ dict (schema_version=1) 왕복 — repository·API 공용 (Design §3.3)."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from src.domain.blueprint.serialization import blueprint_from_dict, blueprint_to_dict
from src.domain.blueprint.value_objects import (
    CURRENT_SCHEMA_VERSION,
    BlueprintAsset,
    Decoration,
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


def _bp() -> DocumentBlueprint:
    now = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
    asset = BlueprintAsset(
        id="a1",
        kind="logo",
        mime="image/png",
        width=10,
        height=5,
        sha256="f" * 64,
        box=RelBox(0.8, 0.02, 0.1, 0.05),
        adopted=True,
    )
    return DocumentBlueprint(
        id="b1",
        name="샘플",
        description="d",
        schema_version=1,
        source_kind="pdf",
        page_count=2,
        style=StyleTokens(
            slide_size=(13.333, 7.5),
            fonts={"heading": "H", "body": "B"},
            sizes={"h1": 28.0, "h2": 20.0, "body": 14.0, "caption": 10.0},
            palette={
                "primary": "#1F3A5F",
                "accent1": "#E07A1F",
                "text": "#222222",
                "bg": "#FFFFFF",
            },
            table_style=TableStyle("#1F3A5F", "#FFFFFF", "#CCCCCC", False),
            header_footer=HeaderFooter("a1", "{n} / {total}", ""),
        ),
        patterns=(
            PagePattern(
                "p1",
                PatternKind.COVER,
                (
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
                "#1F3A5F",
                1,
                "n",
            ),
            PagePattern(
                "p2",
                PatternKind.IMAGE_WITH_NOTES,
                (
                    Slot(
                        "logo",
                        SlotKind.IMAGE,
                        RelBox(0.1, 0.1, 0.3, 0.3),
                        "로고",
                        None,
                        None,
                        "a1",
                    ),
                ),
                None,
                2,
                "",
            ),
        ),
        narrative=Narrative((NarrativeSection("표지", ("p1",), "g"),), "보고체", "ko"),
        assets=(asset,),
        font_mapping={"H": "NanumGothicBold"},
        warnings=("w1",),
        status="active",
        created_at=now,
        updated_at=now,
    )


def test_roundtrip_is_lossless():
    bp = _bp()
    data = blueprint_to_dict(bp)
    assert data["schema_version"] == 1 and isinstance(data["patterns"], list)
    assert (
        data["patterns"][0]["kind"] == "cover"
        and data["patterns"][0]["slots"][0]["kind"] == "title"
    )
    assert blueprint_from_dict(data) == bp


def test_json_safe():
    import json

    json.dumps(blueprint_to_dict(_bp()))  # datetime 은 isoformat 문자열


def test_unknown_schema_version_rejected():
    data = blueprint_to_dict(_bp())
    data["schema_version"] = 99
    with pytest.raises(ValueError):
        blueprint_from_dict(data)


# ── blueprint-style-fidelity §3.4 — schema v2 + v1 폴백 ─────────────────────

_V1_FIXTURE = Path(__file__).parents[2] / "fixtures" / "blueprint" / "golden_v1.json"


def _bp_v2() -> DocumentBlueprint:
    bp = _bp()
    deco = Decoration("deco1", "rect", RelBox(0.0, 0.93, 1.0, 0.07), "#F2F4F5")
    card = Decoration(
        "deco1", "rect", RelBox(0.06, 0.22, 0.88, 0.15), "#F2F4F5", "#CCCCCC"
    )
    style = replace(
        bp.style,
        sizes={**bp.style.sizes, "h3": 16.0, "subtitle": 18.0},
        header_footer=HeaderFooter(
            "a1",
            "{n} / {total}",
            "여신심사부 · 대외비",
            footer_box=RelBox(0.06, 0.95, 0.5, 0.04),
            page_number_box=RelBox(0.9, 0.95, 0.08, 0.04),
            footer_color="#666666",
        ),
        common_decorations=(deco,),
    )
    p1 = bp.patterns[0]
    p1 = replace(
        p1,
        slots=tuple(replace(s, align="center") for s in p1.slots),
        decorations=(card,),
    )
    asset = replace(bp.assets[0], cover_box=RelBox(0.06, 0.07, 0.19, 0.11))
    return replace(
        bp,
        schema_version=CURRENT_SCHEMA_VERSION,
        style=style,
        patterns=(p1, bp.patterns[1]),
        assets=(asset,),
    )


def test_v2_roundtrip_is_lossless():
    bp = _bp_v2()
    data = blueprint_to_dict(bp)
    assert data["schema_version"] == 2
    assert data["style"]["common_decorations"][0]["fill"] == "#F2F4F5"
    assert data["patterns"][0]["decorations"][0]["line"] == "#CCCCCC"
    assert data["patterns"][0]["slots"][0]["align"] == "center"
    assert data["style"]["header_footer"]["footer_box"]["y"] == 0.95
    assert data["assets"][0]["cover_box"]["w"] == 0.19
    json.dumps(data)
    assert blueprint_from_dict(data) == bp


def test_v1_dict_loads_with_defaults_and_keeps_version():
    data = blueprint_to_dict(_bp())  # v1 형태 (새 키 없음)
    for p in data["patterns"]:
        p.pop("decorations", None)
        for s in p["slots"]:
            s.pop("align", None)
    data["style"].pop("common_decorations", None)
    for k in ("footer_box", "page_number_box", "footer_color"):
        data["style"]["header_footer"].pop(k, None)
    data["assets"][0].pop("cover_box", None)
    data["schema_version"] = 1
    bp = blueprint_from_dict(data)
    assert bp.schema_version == 1  # DR-5: 로드 시 버전 보존
    assert bp.style.common_decorations == ()
    assert bp.patterns[0].decorations == ()
    assert bp.patterns[0].slots[0].align == "left"
    assert bp.style.header_footer.footer_box is None
    assert bp.assets[0].cover_box is None


def test_real_golden_v1_fixture_loads():
    data = json.loads(_V1_FIXTURE.read_text(encoding="utf-8"))
    bp = blueprint_from_dict(data)
    assert bp.schema_version == 1 and len(bp.patterns) == 6
    assert bp.style.fonts["heading"] == "Malgun Gothic Bold"
    assert all(p.decorations == () for p in bp.patterns)
    # 재직렬화하면 v2 키가 기본값으로 채워진다
    out = blueprint_to_dict(bp)
    assert out["patterns"][0]["decorations"] == []
    assert out["schema_version"] == 1


# ── blueprint-font-mapping-migration §8.3 시나리오 19 — 순수성 계약 ─────────


def test_from_dict_does_not_normalize_fonts():
    """DR-1: blueprint_from_dict 는 순수 변환이다. 정규화는 호출부 책임."""
    data = blueprint_to_dict(_bp())
    data["style"]["fonts"] = {"heading": "Malgun Gothic Bold", "body": "Malgun Gothic"}
    data["font_mapping"] = {"Malgun Gothic Bold": "Malgun Gothic Bold"}

    bp = blueprint_from_dict(data)

    assert bp.style.fonts["heading"] == "Malgun Gothic Bold"  # 그대로 통과
    assert bp.font_mapping == {"Malgun Gothic Bold": "Malgun Gothic Bold"}


# ── blueprint-render-style-fidelity §8.2 시나리오 4~6 — 하위호환 ─────────────


def test_roundtrip_includes_new_style_fields():
    """시나리오 4 — 신규 필드가 왕복에서 보존된다."""
    bp = _bp()
    style = replace(
        bp.style,
        table_style=replace(bp.style.table_style, zebra_bg="#EEEEEE",
                            border_width_pt=1.5),
        body_line_spacing=1.45,
        body_space_after_pt=33.2,
        chart_label_size_pt=9.0,
        chart_label_bold=False,
    )
    styled = replace(bp, style=style)

    assert blueprint_from_dict(blueprint_to_dict(styled)) == styled


def test_dict_without_new_fields_loads_with_defaults():
    """시나리오 5 (SC-6 핵심) — 신규 필드가 없는 dict 도 로드된다."""
    data = blueprint_to_dict(_bp())
    for key in ("body_line_spacing", "body_space_after_pt",
                "chart_label_size_pt", "chart_label_bold"):
        data["style"].pop(key, None)
    for key in ("zebra_bg", "border_width_pt"):
        data["style"]["table_style"].pop(key, None)

    bp = blueprint_from_dict(data)

    assert bp.style.body_line_spacing == 1.0
    assert bp.style.body_space_after_pt == 0.0
    assert bp.style.chart_label_size_pt == 0.0
    assert bp.style.chart_label_bold is True
    assert bp.style.table_style.zebra_bg == "#F3F4F6"
    assert bp.style.table_style.border_width_pt == 0.0


def test_v1_snapshot_loads_with_new_field_defaults():
    """시나리오 5 (SC-6) — 실제 v1 스냅샷이 수정 없이 로드된다."""
    data = json.loads(_V1_FIXTURE.read_text(encoding="utf-8"))

    bp = blueprint_from_dict(data)

    assert bp.schema_version == 1
    assert bp.style.body_line_spacing == 1.0
    assert bp.style.chart_label_size_pt == 0.0
    assert bp.style.table_style.border_width_pt == 0.0


def test_new_fields_in_dict_are_honoured():
    """시나리오 6 — 값이 담겨 있으면 그대로 반영된다."""
    data = blueprint_to_dict(_bp())
    data["style"]["body_line_spacing"] = 1.45
    data["style"]["chart_label_size_pt"] = 9.0
    data["style"]["table_style"]["border_width_pt"] = 0.75

    bp = blueprint_from_dict(data)

    assert bp.style.body_line_spacing == 1.45
    assert bp.style.chart_label_size_pt == 9.0
    assert bp.style.table_style.border_width_pt == 0.75
