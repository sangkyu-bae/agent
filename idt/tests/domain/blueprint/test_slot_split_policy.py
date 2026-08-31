"""SlotSplitPolicy — 장식 경계로 뭉쳐진 텍스트 슬롯을 쪼갠다.

Design Ref: blueprint-slot-content-fill §8.2 시나리오 1~12 (FR-01·02·06).
"""

import pytest
from src.domain.blueprint.policies import SlotSplitPolicy
from src.domain.blueprint.value_objects import (
    Decoration,
    PagePattern,
    PageStats,
    PatternKind,
    RelBox,
    Slot,
    SlotKind,
    TextSpan,
)

_CAPTION = 10.0


def _span(text: str, x: float, y: float, w: float, h: float, size: float = 13.0):
    return TextSpan(
        text=text, font="F", size=size, bold=False, color="#222222",
        box=RelBox(x, y, w, h),
    )


def _slot(
    sid: str, kind: SlotKind, x: float, y: float, w: float, h: float, max_chars=200
):
    return Slot(sid, kind, RelBox(x, y, w, h), "역할", max_chars, None, None)


def _page(spans) -> PageStats:
    return PageStats(
        number=2, width=960.0, height=540.0,
        spans=tuple(spans), images=(), tables=(), has_text=True,
    )


def _pattern(*slots) -> PagePattern:
    return PagePattern("p1", PatternKind.TEXT, tuple(slots), None, 2, "")


def _deco(did: str, x: float, y: float, w: float, h: float) -> Decoration:
    return Decoration(id=did, shape="rect", box=RelBox(x, y, w, h), fill="#F3F4F6")


# 카드 3장 — 각 카드에 소제목(15pt) + 본문(13pt)
_CARD_DECOS = (
    _deco("d1", 0.06, 0.24, 0.88, 0.17),
    _deco("d2", 0.06, 0.44, 0.88, 0.17),
    _deco("d3", 0.06, 0.64, 0.88, 0.17),
)
_CARD_SPANS = [
    _span("심사 기준 강화", 0.09, 0.26, 0.20, 0.04, size=15.0),
    _span("제조·도소매 업종…", 0.09, 0.33, 0.45, 0.04),
    _span("조기경보 확대", 0.09, 0.46, 0.20, 0.04, size=15.0),
    _span("연체 15일 이상…", 0.09, 0.53, 0.38, 0.04),
    _span("한도 관리", 0.09, 0.66, 0.15, 0.04, size=15.0),
    _span("부문 한도 소진율…", 0.09, 0.73, 0.37, 0.04),
]
_WIDE_SLOT = _slot("bullets", SlotKind.BULLETS, 0.05, 0.20, 0.90, 0.65)


def _ids(pattern: PagePattern) -> list[str]:
    return [s.id for s in pattern.slots]


# ── 시나리오 1~4: 분할 성립 (FR-01·FR-02) ──────────────────────────────────


def test_splits_slot_into_one_per_decoration_group():
    out, warnings = SlotSplitPolicy.apply(
        _page(_CARD_SPANS), _pattern(_WIDE_SLOT), _CARD_DECOS, _CAPTION
    )

    assert _ids(out) == ["bullets", "bullets2", "bullets3"]
    assert warnings == ()


def test_split_slot_ids_follow_existing_suffix_rule():
    """DR-4 — _pattern_from_draft 와 같은 규칙. 새 id 체계를 만들지 않는다."""
    out, _ = SlotSplitPolicy.apply(
        _page(_CARD_SPANS), _pattern(_WIDE_SLOT), _CARD_DECOS, _CAPTION
    )

    assert _ids(out) == ["bullets", "bullets2", "bullets3"]


def test_split_slots_inherit_source_attributes():
    source = _slot("bullets", SlotKind.BULLETS, 0.05, 0.20, 0.90, 0.65, max_chars=321)
    out, _ = SlotSplitPolicy.apply(
        _page(_CARD_SPANS), _pattern(source), _CARD_DECOS, _CAPTION
    )

    for slot in out.slots:
        assert slot.kind is SlotKind.BULLETS
        assert slot.role == "역할"
        assert slot.max_chars == 321
        assert slot.align == source.align


def test_split_slots_are_ordered_by_y_and_boxed_to_group_union():
    out, _ = SlotSplitPolicy.apply(
        _page(_CARD_SPANS), _pattern(_WIDE_SLOT), _CARD_DECOS, _CAPTION
    )

    tops = [s.box.y for s in out.slots]
    assert tops == sorted(tops)
    assert round(out.slots[0].box.y, 3) == 0.26   # 첫 카드 소제목 상단
    assert round(out.slots[1].box.y, 3) == 0.46
    assert round(out.slots[2].box.y, 3) == 0.66
    # 각 슬롯이 자기 장식 안에 완전히 포함
    for slot, deco in zip(out.slots, _CARD_DECOS, strict=True):
        assert deco.box.y <= slot.box.y
        assert slot.box.y + slot.box.h <= deco.box.y + deco.box.h + 1e-9


# ── 시나리오 5~7: 분할 안 함 (FR-06) ───────────────────────────────────────


def test_single_decoration_group_is_not_split():
    one = (_deco("d1", 0.06, 0.24, 0.88, 0.50),)
    out, warnings = SlotSplitPolicy.apply(
        _page(_CARD_SPANS[:2]), _pattern(_WIDE_SLOT), one, _CAPTION
    )

    assert _ids(out) == ["bullets"]
    assert warnings == ()


def test_unassigned_span_blocks_split():
    """장식에 속하지 않는 span 이 하나라도 있으면 분할하지 않는다."""
    # 슬롯(0.20~0.85) 안이지만 어떤 장식(마지막 0.64~0.81)에도 속하지 않는 위치
    spans = [*_CARD_SPANS, _span("떠 있는 문장", 0.09, 0.82, 0.30, 0.02)]

    out, _ = SlotSplitPolicy.apply(
        _page(spans), _pattern(_WIDE_SLOT), _CARD_DECOS, _CAPTION
    )

    assert _ids(out) == ["bullets"]


def test_pattern_without_decorations_is_unchanged():
    pattern = _pattern(_WIDE_SLOT)
    out, warnings = SlotSplitPolicy.apply(_page(_CARD_SPANS), pattern, (), _CAPTION)

    assert out is pattern
    assert warnings == ()


# ── 시나리오 8~10: 대상 한정·경계 ──────────────────────────────────────────


@pytest.mark.parametrize(
    "kind", [SlotKind.TABLE, SlotKind.CHART, SlotKind.IMAGE, SlotKind.FOOTER]
)
def test_non_text_slots_are_never_split(kind):
    slot = _slot("s", kind, 0.05, 0.20, 0.90, 0.65)
    out, _ = SlotSplitPolicy.apply(
        _page(_CARD_SPANS), _pattern(slot), _CARD_DECOS, _CAPTION
    )

    assert _ids(out) == ["s"]


def test_narrow_accent_bar_cannot_own_a_span():
    """액센트 바(폭 0.008)는 span 을 포함하지 못해 그룹에서 자동 제외된다."""
    bars = tuple(
        _deco(f"bar{i}", d.box.x, d.box.y, 0.008, d.box.h)
        for i, d in enumerate(_CARD_DECOS, start=1)
    )
    out, _ = SlotSplitPolicy.apply(
        _page(_CARD_SPANS), _pattern(_WIDE_SLOT), (*_CARD_DECOS, *bars), _CAPTION
    )

    assert _ids(out) == ["bullets", "bullets2", "bullets3"]


def test_nested_decorations_resolve_by_pattern_order():
    """중첩 장식이 같은 span 을 포함하면 등장 순서로 결정론을 확보한다."""
    outer = _deco("outer", 0.0, 0.20, 1.0, 0.70)
    decos = (outer, *_CARD_DECOS)  # outer 가 먼저 → 전부 outer 소유 → 그룹 1개

    out, _ = SlotSplitPolicy.apply(
        _page(_CARD_SPANS), _pattern(_WIDE_SLOT), decos, _CAPTION
    )

    assert _ids(out) == ["bullets"]  # 그룹 1개라 분할 안 함


# ── 시나리오 11~12: 멱등·푸터 ──────────────────────────────────────────────


def test_applying_twice_is_idempotent():
    once, _ = SlotSplitPolicy.apply(
        _page(_CARD_SPANS), _pattern(_WIDE_SLOT), _CARD_DECOS, _CAPTION
    )
    twice, _ = SlotSplitPolicy.apply(
        _page(_CARD_SPANS), once, _CARD_DECOS, _CAPTION
    )

    assert _ids(twice) == _ids(once)


def test_footer_band_spans_are_excluded_from_grouping():
    footer_deco = _deco("fbar", 0.0, 0.92, 1.0, 0.08)
    footer = _span("여신심사부 · 대외비", 0.06, 0.95, 0.17, 0.02, size=_CAPTION)
    spans = [*_CARD_SPANS, footer]

    out, _ = SlotSplitPolicy.apply(
        _page(spans), _pattern(_WIDE_SLOT), (*_CARD_DECOS, footer_deco), _CAPTION
    )

    assert _ids(out) == ["bullets", "bullets2", "bullets3"]  # 푸터가 4번째 그룹이 아님
