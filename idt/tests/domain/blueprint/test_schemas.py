"""LLM Draft 스키마 (Design §3.1 schemas.py) — strict 호환 + 신뢰 경계."""

import dataclasses
import typing

import pytest
from pydantic import BaseModel, ValidationError
from src.domain.blueprint.schemas import (
    DRAFT_PATTERN_COPIED_FIELDS,
    SERVER_COMPUTED_PATTERN_FIELDS,
    NarrativeDraft,
    PagePatternDraft,
    SlideContentDraft,
    SlidePlanDraft,
    SlotDraft,
)
from src.domain.blueprint.value_objects import PagePattern


def _walk(model: type[BaseModel], seen=None):
    seen = seen or set()
    if model in seen:
        return
    seen.add(model)
    for name, field in model.model_fields.items():
        ann = field.annotation
        yield model.__name__, name, ann
        for sub in _nested_models(ann):
            yield from _walk(sub, seen)


def _nested_models(ann):
    origin = typing.get_origin(ann)
    if origin is None:
        if isinstance(ann, type) and issubclass(ann, BaseModel):
            yield ann
        return
    for arg in typing.get_args(ann):
        yield from _nested_models(arg)


@pytest.mark.parametrize(
    "root", [PagePatternDraft, NarrativeDraft, SlidePlanDraft, SlideContentDraft]
)
def test_no_dict_or_any_anywhere_in_draft_schemas(root):
    """위키 structured-output-strict-schema: dict/Any 금지 (재귀)."""
    for model_name, field, ann in _walk(root):
        text = repr(ann)
        assert "dict" not in text.lower() and "Any" not in text, (
            f"{model_name}.{field}: {ann}"
        )


@pytest.mark.parametrize(
    "root", [PagePatternDraft, NarrativeDraft, SlidePlanDraft, SlideContentDraft]
)
def test_extra_forbidden(root):
    assert root.model_config.get("extra") == "forbid"


def test_page_pattern_draft_kind_is_literal_and_box_validated():
    ok = PagePatternDraft(
        kind="cover",
        slots=[
            SlotDraft(
                kind="title", x=0.1, y=0.1, w=0.8, h=0.2, role="제목", max_chars=40
            )
        ],
        layout_notes="",
    )
    assert ok.kind == "cover"
    with pytest.raises(ValidationError):
        PagePatternDraft(kind="poster", slots=[], layout_notes="")
    with pytest.raises(ValidationError):
        SlotDraft(kind="title", x=0.6, y=0.1, w=0.8, h=0.2, role="", max_chars=None)


def test_draft_pattern_fields_disjoint_from_server_fields_and_cover_vo():
    """Draft 가 채우는 필드 ∪ 서버 필드 == PagePattern 필드 (신뢰 경계 고정)."""
    vo_fields = {f.name for f in dataclasses.fields(PagePattern)}
    assert DRAFT_PATTERN_COPIED_FIELDS.isdisjoint(SERVER_COMPUTED_PATTERN_FIELDS)
    assert DRAFT_PATTERN_COPIED_FIELDS | SERVER_COMPUTED_PATTERN_FIELDS == vo_fields
    draft_fields = set(PagePatternDraft.model_fields)
    assert SERVER_COMPUTED_PATTERN_FIELDS.isdisjoint(draft_fields)


def test_slide_plan_draft_limits_and_slot_content_union_shape():
    plan = SlidePlanDraft(
        slides=[
            {"pattern_id": "p1", "title": "t", "intent": "i", "data_hint": ""},
        ]
    )
    assert plan.slides[0].pattern_id == "p1"
    content = SlideContentDraft(
        slots=[
            {
                "slot_id": "title",
                "text": "제목",
                "bullets": None,
                "table": None,
                "chart": None,
            },
            {
                "slot_id": "chart",
                "text": None,
                "bullets": None,
                "table": None,
                "chart": {
                    "type": "bar",
                    "categories": ["1Q", "2Q"],
                    "series": [{"name": "연체율", "values": [1.2, 1.5]}],
                    "unit": "%",
                },
            },
        ]
    )
    assert content.slots[1].chart.series[0].values == [1.2, 1.5]
    with pytest.raises(ValidationError):
        SlideContentDraft(slots=[{"slot_id": "x", "text": "a", "extra": 1}])


# ── blueprint-style-fidelity §3.2 — SlotDraft.align ─────────────────────────


def test_slot_draft_align_default_and_literal():
    from pydantic import ValidationError
    from src.domain.blueprint.schemas import SlotDraft

    s = SlotDraft(kind="title", x=0.1, y=0.1, w=0.5, h=0.1, role="r")
    assert s.align == "left"
    centered = SlotDraft(kind="title", x=0, y=0, w=1, h=1, role="r", align="center")
    assert centered.align == "center"
    with pytest.raises(ValidationError):
        SlotDraft(kind="title", x=0, y=0, w=1, h=1, role="r", align="middle")
