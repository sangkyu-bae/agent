"""TocContentPolicy — 목차를 계획된 슬라이드 제목에서 결정론적으로 만든다.

Design Ref: blueprint-slot-content-fill §8.2 시나리오 13~20 (FR-04).
"""

from src.domain.blueprint.policies import TocContentPolicy
from src.domain.blueprint.value_objects import (
    PagePattern,
    PatternKind,
    RelBox,
    SlidePlan,
    Slot,
    SlotKind,
)


def _slot(sid: str, kind: SlotKind) -> Slot:
    return Slot(sid, kind, RelBox(0.05, 0.1, 0.9, 0.7), "역할", None, None, None)


def _toc_pattern(*slots: Slot) -> PagePattern:
    return PagePattern("p2", PatternKind.TOC, tuple(slots), None, 2, "")


_TOC_SLOTS = (_slot("title", SlotKind.TITLE), _slot("bullets", SlotKind.BULLETS))


def _plan(index: int, pattern_id: str, title: str) -> SlidePlan:
    return SlidePlan(index, pattern_id, title, "의도", "힌트")


def _kinds(**mapping: PatternKind) -> dict[str, PatternKind]:
    return dict(mapping)


_PLANS = [
    _plan(1, "p1", "표지 제목"),
    _plan(2, "p2", "목차"),
    _plan(3, "p3", "1. 요약 및 핵심 메시지"),
    _plan(4, "p4", "2. 연체율 추이 분석"),
    _plan(5, "p5", "3. 포트폴리오 현황"),
]
_KINDS = _kinds(
    p1=PatternKind.COVER,
    p2=PatternKind.TOC,
    p3=PatternKind.SECTION_LEAD,
    p4=PatternKind.CHART_WITH_NOTES,
    p5=PatternKind.TABLE,
)


def _bullets(content) -> tuple[str, ...]:
    return next(c.bullets for c in content.slots if c.slot_id == "bullets")


# ── 시나리오 13~16: 항목 구성 (FR-04, DR-7) ────────────────────────────────


def test_excludes_cover_and_the_toc_slide_itself():
    out, warnings = TocContentPolicy.apply(
        _PLANS[1], _PLANS, _KINDS, _toc_pattern(*_TOC_SLOTS)
    )

    assert out is not None
    assert _bullets(out) == (
        "1. 요약 및 핵심 메시지",
        "2. 연체율 추이 분석",
        "3. 포트폴리오 현황",
    )
    assert warnings == ()


def test_items_follow_plan_order():
    shuffled = [_PLANS[1], _PLANS[4], _PLANS[2], _PLANS[0], _PLANS[3]]
    out, _ = TocContentPolicy.apply(
        _PLANS[1], shuffled, _KINDS, _toc_pattern(*_TOC_SLOTS)
    )

    assert _bullets(out) == (
        "3. 포트폴리오 현황",
        "1. 요약 및 핵심 메시지",
        "2. 연체율 추이 분석",
    )


def test_items_carry_no_ordinal_prefix():
    """DR-6 — 번호는 렌더러 _bullets TOC 분기가 붙인다. 넣으면 '1. 1. …' 이 된다."""
    plans = [_PLANS[1], _plan(3, "p3", "요약")]
    kinds = _kinds(p2=PatternKind.TOC, p3=PatternKind.TEXT)

    out, _ = TocContentPolicy.apply(plans[0], plans, kinds, _toc_pattern(*_TOC_SLOTS))

    assert _bullets(out) == ("요약",)


def test_blank_titles_are_skipped():
    plans = [_PLANS[1], _plan(3, "p3", "   "), _plan(4, "p4", "본문")]
    kinds = _kinds(p2=PatternKind.TOC, p3=PatternKind.TEXT, p4=PatternKind.TEXT)

    out, _ = TocContentPolicy.apply(plans[0], plans, kinds, _toc_pattern(*_TOC_SLOTS))

    assert _bullets(out) == ("본문",)


# ── 시나리오 17: 상한 (DR-8) ───────────────────────────────────────────────


def test_items_over_cap_are_truncated_with_warning():
    plans = [_PLANS[1]] + [_plan(i, f"px{i}", f"섹션 {i}") for i in range(3, 20)]
    kinds = {"p2": PatternKind.TOC}
    kinds.update({f"px{i}": PatternKind.TEXT for i in range(3, 20)})

    out, warnings = TocContentPolicy.apply(
        plans[0], plans, kinds, _toc_pattern(*_TOC_SLOTS)
    )

    assert len(_bullets(out)) == 12
    assert _bullets(out)[0] == "섹션 3"  # 앞에서부터
    assert len(warnings) == 1 and "12" in warnings[0]


# ── 시나리오 18~20: 폴백·title 슬롯 ────────────────────────────────────────


def test_no_items_falls_back_to_writer():
    plans = [_PLANS[1]]  # 목차 자신뿐
    out, warnings = TocContentPolicy.apply(
        plans[0], plans, {"p2": PatternKind.TOC}, _toc_pattern(*_TOC_SLOTS)
    )

    assert out is None
    assert len(warnings) == 1


def test_pattern_without_bullets_slot_falls_back_to_writer():
    out, warnings = TocContentPolicy.apply(
        _PLANS[1], _PLANS, _KINDS, _toc_pattern(_slot("title", SlotKind.TITLE))
    )

    assert out is None
    assert len(warnings) == 1


def test_title_slot_is_filled_from_plan_title():
    out, _ = TocContentPolicy.apply(
        _PLANS[1], _PLANS, _KINDS, _toc_pattern(*_TOC_SLOTS)
    )

    title = next(c for c in out.slots if c.slot_id == "title")
    assert title.text == "목차"


def test_pattern_without_title_slot_still_produces_bullets():
    out, _ = TocContentPolicy.apply(
        _PLANS[1], _PLANS, _KINDS, _toc_pattern(_slot("bullets", SlotKind.BULLETS))
    )

    assert out is not None
    assert [c.slot_id for c in out.slots] == ["bullets"]
