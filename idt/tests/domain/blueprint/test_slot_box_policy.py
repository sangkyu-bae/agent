"""SlotBoxPolicy — 비전 추정 슬롯 좌표를 실측 span 으로 스냅.

Design Ref: blueprint-slot-box-snap §8.2 시나리오 1~19 (FR-01~06).
"""

import pytest
from src.domain.blueprint.policies import SlotBoxPolicy
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


def _span(text: str, x: float, y: float, w: float, h: float, size: float = 14.0):
    return TextSpan(
        text=text, font="F", size=size, bold=False, color="#222222",
        box=RelBox(x, y, w, h),
    )


def _slot(sid: str, kind: SlotKind, x: float, y: float, w: float, h: float):
    return Slot(sid, kind, RelBox(x, y, w, h), "역할", None, None, None)


def _page(spans, number: int = 2) -> PageStats:
    return PageStats(
        number=number, width=960.0, height=540.0,
        spans=tuple(spans), images=(), tables=(), has_text=True,
    )


def _pattern(*slots, pid: str = "p1", kind: PatternKind = PatternKind.TEXT):
    return PagePattern(pid, kind, tuple(slots), None, 2, "")


def _deco(did: str, x: float, y: float, w: float, h: float) -> Decoration:
    return Decoration(id=did, shape="rect", box=RelBox(x, y, w, h), fill="#F3F4F6")


def _box_of(pattern: PagePattern, sid: str) -> RelBox:
    slot = pattern.slot(sid)
    assert slot is not None
    return slot.box


# ── 시나리오 1~5: union·배정 (FR-01, FR-02) ─────────────────────────────────


def test_union_takes_min_origin_and_max_extent():
    page = _page([
        _span("a", 0.10, 0.20, 0.30, 0.04),
        _span("b", 0.08, 0.25, 0.50, 0.04),
        _span("c", 0.12, 0.30, 0.20, 0.04),
    ])
    pattern = _pattern(_slot("text", SlotKind.TEXT, 0.05, 0.15, 0.90, 0.30))

    out, warnings = SlotBoxPolicy.apply(page, pattern, (), _CAPTION)

    box = _box_of(out, "text")
    assert (round(box.x, 3), round(box.y, 3)) == (0.08, 0.20)
    assert round(box.w, 3) == round(0.58 - 0.08, 3)  # max(x+w)=0.58
    assert warnings == ()


def test_span_is_assigned_to_slot_containing_its_center():
    page = _page([_span("a", 0.10, 0.20, 0.10, 0.04)])
    pattern = _pattern(
        _slot("title", SlotKind.TITLE, 0.05, 0.05, 0.90, 0.10),
        _slot("text", SlotKind.TEXT, 0.05, 0.15, 0.90, 0.30),
    )

    out, _ = SlotBoxPolicy.apply(page, pattern, (), _CAPTION)

    assert round(_box_of(out, "text").y, 3) == 0.20  # text 로 배정됨
    assert _box_of(out, "title") == RelBox(0.05, 0.05, 0.90, 0.10)  # 폴백 유지


def test_span_outside_every_slot_is_dropped():
    page = _page([
        _span("in", 0.10, 0.20, 0.10, 0.04),
        _span("out", 0.60, 0.70, 0.30, 0.04),  # 어떤 슬롯에도 없음
    ])
    pattern = _pattern(_slot("text", SlotKind.TEXT, 0.05, 0.15, 0.90, 0.20))

    out, _ = SlotBoxPolicy.apply(page, pattern, (), _CAPTION)

    box = _box_of(out, "text")
    assert (round(box.x, 3), round(box.y, 3)) == (0.10, 0.20)
    assert round(box.w, 3) == 0.10  # out 의 우변(0.90)이 폭에 반영되지 않았다


def test_overlapping_slots_pick_nearest_center_y():
    page = _page([_span("a", 0.10, 0.40, 0.10, 0.04)])  # 중심 y=0.42
    pattern = _pattern(
        _slot("text", SlotKind.TEXT, 0.05, 0.10, 0.90, 0.60),   # 중심 0.40 — 가까움
        _slot("text2", SlotKind.TEXT, 0.05, 0.10, 0.90, 0.80),  # 중심 0.50
    )

    out, _ = SlotBoxPolicy.apply(page, pattern, (), _CAPTION)

    assert round(_box_of(out, "text").y, 3) == 0.40
    assert _box_of(out, "text2") == RelBox(0.05, 0.10, 0.90, 0.80)  # 미배정


def test_tie_on_center_distance_breaks_by_slot_id():
    page = _page([_span("a", 0.10, 0.40, 0.10, 0.04)])
    pattern = _pattern(  # 동일 박스 → 중심 거리 동점
        _slot("b_slot", SlotKind.TEXT, 0.05, 0.10, 0.90, 0.60),
        _slot("a_slot", SlotKind.TEXT, 0.05, 0.10, 0.90, 0.60),
    )

    out, _ = SlotBoxPolicy.apply(page, pattern, (), _CAPTION)

    assert round(_box_of(out, "a_slot").y, 3) == 0.40  # 사전순 앞선 쪽
    assert _box_of(out, "b_slot") == RelBox(0.05, 0.10, 0.90, 0.60)


# ── 시나리오 6~7: 푸터 배제 (FR-04) ─────────────────────────────────────────


def test_footer_band_caption_span_is_excluded():
    page = _page([
        _span("본문", 0.10, 0.20, 0.10, 0.04),
        _span("여신심사부 · 대외비", 0.06, 0.95, 0.17, 0.02, size=_CAPTION),
    ])
    pattern = _pattern(_slot("text", SlotKind.TEXT, 0.05, 0.10, 0.90, 0.88))

    out, _ = SlotBoxPolicy.apply(page, pattern, (), _CAPTION)

    box = _box_of(out, "text")
    assert round(box.y + box.h, 3) <= 0.88  # 푸터 span 이 union 에 없음


def test_footer_band_body_size_span_is_kept():
    """크기 조건을 만족하지 않으면 하단 밴드에 있어도 푸터가 아니다."""
    page = _page([_span("큰 글씨", 0.10, 0.90, 0.30, 0.05, size=20.0)])
    pattern = _pattern(_slot("text", SlotKind.TEXT, 0.05, 0.10, 0.90, 0.88))

    out, _ = SlotBoxPolicy.apply(page, pattern, (), _CAPTION)

    assert round(_box_of(out, "text").y, 3) == 0.90


# ── 시나리오 8~11: 높이 경계 (FR-03) ───────────────────────────────────────


def test_height_extends_to_next_text_slot_top():
    page = _page([
        _span("제목", 0.06, 0.08, 0.20, 0.06),
        _span("본문", 0.06, 0.40, 0.30, 0.04),
    ])
    pattern = _pattern(
        _slot("title", SlotKind.TITLE, 0.05, 0.05, 0.90, 0.10),
        _slot("text", SlotKind.TEXT, 0.05, 0.30, 0.90, 0.30),
    )

    out, _ = SlotBoxPolicy.apply(page, pattern, (), _CAPTION)

    title = _box_of(out, "title")
    assert round(title.y + title.h, 3) == 0.40  # 다음 슬롯 스냅 후 top


def test_height_extends_to_non_text_slot_top():
    """DR-4 회귀 방어 — 표 슬롯을 경계에서 빠뜨리면 제목이 표를 삼킨다."""
    page = _page([_span("제목", 0.06, 0.08, 0.20, 0.06)])
    pattern = _pattern(
        _slot("title", SlotKind.TITLE, 0.05, 0.05, 0.90, 0.10),
        _slot("table", SlotKind.TABLE, 0.05, 0.20, 0.90, 0.50),
    )

    out, _ = SlotBoxPolicy.apply(page, pattern, (), _CAPTION)

    title = _box_of(out, "title")
    assert round(title.y + title.h, 3) == 0.20
    assert _box_of(out, "table") == RelBox(0.05, 0.20, 0.90, 0.50)  # 표는 무변경


def test_height_extends_to_decoration_top():
    page = _page([_span("제목", 0.06, 0.08, 0.20, 0.06)])
    pattern = _pattern(_slot("title", SlotKind.TITLE, 0.05, 0.05, 0.90, 0.10))

    deco = _deco("d1", 0.0, 0.30, 1.0, 0.10)
    out, _ = SlotBoxPolicy.apply(page, pattern, (deco,), _CAPTION)

    title = _box_of(out, "title")
    assert round(title.y + title.h, 3) == 0.30


def test_height_falls_back_to_footer_band():
    page = _page([_span("본문", 0.06, 0.20, 0.30, 0.04)])
    pattern = _pattern(_slot("text", SlotKind.TEXT, 0.05, 0.10, 0.90, 0.30))

    out, _ = SlotBoxPolicy.apply(page, pattern, (), _CAPTION)

    text = _box_of(out, "text")
    assert round(text.y + text.h, 3) == 0.88


# ── 시나리오 12~13: 장식 캡 (DR-5) ─────────────────────────────────────────


def test_height_is_capped_by_enclosing_decoration():
    page = _page([_span("요약", 0.09, 0.25, 0.70, 0.04)])
    pattern = _pattern(_slot("text", SlotKind.TEXT, 0.05, 0.20, 0.90, 0.20))
    enclosing = _deco("hl", 0.06, 0.22, 0.88, 0.15)  # 0.22 ~ 0.37 이 union 포함

    out, _ = SlotBoxPolicy.apply(page, pattern, (enclosing,), _CAPTION)

    text = _box_of(out, "text")
    assert round(text.y + text.h, 3) == 0.37  # 푸터(0.88)가 아니라 장식 하단


def test_partially_overlapping_decoration_does_not_cap():
    page = _page([_span("요약", 0.09, 0.25, 0.70, 0.04)])
    pattern = _pattern(_slot("text", SlotKind.TEXT, 0.05, 0.20, 0.90, 0.20))
    partial = _deco("hl", 0.50, 0.22, 0.40, 0.15)  # union 을 완전히 감싸지 않음

    out, _ = SlotBoxPolicy.apply(page, pattern, (partial,), _CAPTION)

    text = _box_of(out, "text")
    assert round(text.y + text.h, 3) == 0.88  # 캡 없음 → 푸터 밴드까지


# ── 시나리오 14~17: 폴백·대상 한정 (FR-05) ─────────────────────────────────


def test_slot_without_assigned_span_keeps_vision_box_and_warns():
    page = _page([_span("본문", 0.10, 0.40, 0.10, 0.04)])
    pattern = _pattern(
        _slot("title", SlotKind.TITLE, 0.05, 0.05, 0.90, 0.10),
        _slot("text", SlotKind.TEXT, 0.05, 0.30, 0.90, 0.30),
    )

    out, warnings = SlotBoxPolicy.apply(page, pattern, (), _CAPTION)

    assert _box_of(out, "title") == RelBox(0.05, 0.05, 0.90, 0.10)
    assert len(warnings) == 1 and "title" in warnings[0]


def test_page_without_spans_returns_pattern_unchanged():
    pattern = _pattern(_slot("title", SlotKind.TITLE, 0.05, 0.05, 0.90, 0.10))

    out, warnings = SlotBoxPolicy.apply(_page([]), pattern, (), _CAPTION)

    assert out is pattern
    assert warnings == ()


@pytest.mark.parametrize("kind", [SlotKind.TABLE, SlotKind.CHART, SlotKind.IMAGE])
def test_non_text_slots_are_never_snapped(kind):
    page = _page([_span("x", 0.30, 0.40, 0.10, 0.04)])
    pattern = _pattern(_slot("s", kind, 0.05, 0.30, 0.90, 0.30))

    out, _ = SlotBoxPolicy.apply(page, pattern, (), _CAPTION)

    assert _box_of(out, "s") == RelBox(0.05, 0.30, 0.90, 0.30)


def test_footer_slot_is_never_snapped():
    page = _page([_span("x", 0.30, 0.95, 0.10, 0.04, size=20.0)])
    pattern = _pattern(_slot("footer", SlotKind.FOOTER, 0.05, 0.93, 0.90, 0.05))

    out, _ = SlotBoxPolicy.apply(page, pattern, (), _CAPTION)

    assert _box_of(out, "footer") == RelBox(0.05, 0.93, 0.90, 0.05)


# ── 시나리오 18~19: 불변식·멱등 (FR-06) ────────────────────────────────────


def test_result_box_stays_inside_slide_bounds():
    page = _page([_span("가장자리", 0.94, 0.86, 0.06, 0.04)])
    pattern = _pattern(_slot("text", SlotKind.TEXT, 0.90, 0.80, 0.10, 0.15))

    out, _ = SlotBoxPolicy.apply(page, pattern, (), _CAPTION)

    b = _box_of(out, "text")
    assert 0.0 <= b.x <= 0.99 and 0.0 <= b.y <= 0.99
    assert b.w >= 0.01 and b.h >= 0.01
    assert b.x + b.w <= 1.0 + 1e-9 and b.y + b.h <= 1.0 + 1e-9


def test_applying_twice_is_idempotent():
    page = _page([
        _span("제목", 0.06, 0.08, 0.20, 0.06),
        _span("본문", 0.09, 0.40, 0.30, 0.04),
    ])
    pattern = _pattern(
        _slot("title", SlotKind.TITLE, 0.05, 0.05, 0.90, 0.10),
        _slot("text", SlotKind.TEXT, 0.05, 0.30, 0.90, 0.30),
    )

    once, _ = SlotBoxPolicy.apply(page, pattern, (), _CAPTION)
    twice, _ = SlotBoxPolicy.apply(page, once, (), _CAPTION)

    assert twice == once
