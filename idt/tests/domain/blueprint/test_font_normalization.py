"""normalize_blueprint_fonts — 저장된 블루프린트의 폰트명 정규화.

Design Ref: blueprint-font-mapping-migration §8.2 시나리오 7~14 (FR-01/02/05).
"""

from datetime import UTC, datetime

from src.domain.blueprint.font_normalization import normalize_blueprint_fonts
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

_NOW = datetime(2026, 8, 25, tzinfo=UTC)


def _bp(fonts: dict[str, str], mapping: dict[str, str]) -> DocumentBlueprint:
    return DocumentBlueprint(
        id="b1",
        name="샘플",
        description="d",
        schema_version=2,
        source_kind="pdf",
        page_count=1,
        style=StyleTokens(
            slide_size=(13.333, 7.5),
            fonts=dict(fonts),
            sizes={"h1": 34.0, "h2": 24.0, "body": 13.0, "caption": 9.0},
            palette={
                "primary": "#1F3A5F",
                "accent1": "#E07A1F",
                "text": "#222222",
                "bg": "#FFFFFF",
            },
            table_style=TableStyle("#1F3A5F", "#FFFFFF", "#CCCCCC", True),
            header_footer=HeaderFooter(None, "{n} / {total}", "푸터"),
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
                        60,
                        None,
                        None,
                    ),
                ),
                None,
                1,
                "n",
            ),
        ),
        narrative=Narrative((NarrativeSection("표지", ("p1",), "g"),), "보고체", "ko"),
        assets=(),
        font_mapping=dict(mapping),
        warnings=("w1",),
        status="active",
        created_at=_NOW,
        updated_at=_NOW,
    )


_POLLUTED_FONTS = {"heading": "Malgun Gothic Bold", "body": "Malgun Gothic Regular"}


# ── 시나리오 7: style.fonts 정규화 (FR-01) ──────────────────────────────────


def test_style_fonts_are_normalized_to_family_names():
    out = normalize_blueprint_fonts(_bp(_POLLUTED_FONTS, {}))
    assert out.style.fonts == {"heading": "Malgun Gothic", "body": "Malgun Gothic"}


# ── 시나리오 8·9: font_mapping 키·값 정규화와 충돌 (FR-02, DR-6) ────────────


def test_mapping_keys_and_values_are_normalized_and_collapsed():
    mapping = {
        "Malgun Gothic Bold": "NanumGothic",
        "Malgun Gothic Regular": "NanumGothic",
    }
    out = normalize_blueprint_fonts(_bp(_POLLUTED_FONTS, mapping))
    assert out.font_mapping == {"Malgun Gothic": "NanumGothic"}


def test_mapping_conflict_picks_alphabetically_first_value():
    mapping = {"Malgun Gothic Bold": "B Font", "Malgun Gothic Regular": "A Font"}
    out = normalize_blueprint_fonts(_bp(_POLLUTED_FONTS, mapping))
    assert out.font_mapping == {"Malgun Gothic": "A Font"}


def test_mapping_values_are_normalized_too():
    mapping = {"Malgun Gothic Bold": "NanumSquare ExtraBold"}
    out = normalize_blueprint_fonts(_bp(_POLLUTED_FONTS, mapping))
    assert out.font_mapping == {"Malgun Gothic": "NanumSquare"}


def test_identity_mapping_stays_resolvable_after_normalization():
    """오염 실사례 — 항등 매핑도 조회 키와 함께 접혀 렌더러 조회가 성립한다 (DR-2)."""
    mapping = {
        "Malgun Gothic Bold": "Malgun Gothic Bold",
        "Malgun Gothic Regular": "Malgun Gothic Regular",
    }
    out = normalize_blueprint_fonts(_bp(_POLLUTED_FONTS, mapping))
    assert out.font_mapping == {"Malgun Gothic": "Malgun Gothic"}
    for role in ("heading", "body"):
        key = out.style.fonts[role]
        assert out.font_mapping[key] == "Malgun Gothic"  # 조회가 빗나가지 않는다


# ── 시나리오 10·11: 멱등성 (FR-05) ──────────────────────────────────────────


def test_already_normalized_blueprint_is_returned_unchanged():
    clean = _bp({"heading": "Malgun Gothic", "body": "Malgun Gothic"}, {"A": "B"})
    assert normalize_blueprint_fonts(clean) is clean


def test_normalization_is_idempotent():
    once = normalize_blueprint_fonts(_bp(_POLLUTED_FONTS, {"Malgun Gothic Bold": "X"}))
    twice = normalize_blueprint_fonts(once)
    assert twice == once


# ── 시나리오 12·13: 빈 값·빈 맵 (§6.1) ──────────────────────────────────────


def test_empty_font_name_is_kept_without_error():
    out = normalize_blueprint_fonts(
        _bp({"heading": "", "body": "Malgun Gothic Bold"}, {})
    )
    assert out.style.fonts == {"heading": "", "body": "Malgun Gothic"}


def test_empty_mapping_still_normalizes_style_fonts():
    out = normalize_blueprint_fonts(_bp(_POLLUTED_FONTS, {}))
    assert out.font_mapping == {}
    assert out.style.fonts["heading"] == "Malgun Gothic"


def test_protected_family_survives_blueprint_normalization():
    """Plan SC-7 — 실존 패밀리는 블루프린트 경로에서도 훼손되지 않는다."""
    out = normalize_blueprint_fonts(
        _bp({"heading": "Times New Roman", "body": "Arial Black"}, {})
    )
    assert out.style.fonts == {"heading": "Times New Roman", "body": "Arial Black"}


# ── 시나리오 14: 폰트 외 필드 불변 ──────────────────────────────────────────


def test_non_font_fields_are_untouched():
    source = _bp(_POLLUTED_FONTS, {"Malgun Gothic Bold": "X"})
    out = normalize_blueprint_fonts(source)
    assert out.patterns == source.patterns
    assert out.narrative == source.narrative
    assert out.assets == source.assets
    assert out.warnings == source.warnings
    assert (out.id, out.name, out.status) == (source.id, source.name, source.status)
    assert out.schema_version == source.schema_version  # 버전 승격은 하지 않는다
    assert out.style.palette == source.style.palette
    assert out.style.sizes == source.style.sizes
    assert out.style.header_footer == source.style.header_footer
