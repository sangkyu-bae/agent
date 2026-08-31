"""Design §3.1 — DescriptionDraft(LLM 전용) strict 호환 + 서버 계산 필드 분리.

FR-07/08.
"""

from dataclasses import fields as dc_fields
from typing import Any, get_args, get_origin

import pytest
from pydantic import BaseModel
from src.domain.multimodal.schemas import (
    DRAFT_COPIED_FIELDS,
    SERVER_COMPUTED_FIELDS,
    DescriptionDraft,
)
from src.domain.multimodal.value_objects import MultimodalElement


def _nested_models(ann):
    if isinstance(ann, type) and issubclass(ann, BaseModel):
        yield ann
    for a in get_args(ann):
        yield from _nested_models(a)


def _walk(model: type[BaseModel], seen=None):
    seen = seen if seen is not None else set()
    if model in seen:
        return
    seen.add(model)
    for name, f in model.model_fields.items():
        yield model, name, f.annotation
        for sub in _nested_models(f.annotation):
            yield from _walk(sub, seen)


def _flatten(ann):
    yield ann
    for a in get_args(ann):
        yield from _flatten(a)


def test_draft_has_no_free_key_dict_or_any():
    """OpenAI strict: dict[str, X]/Any 하나가 전체 strict 를 무효화.

    위키 structured-output-strict-schema.
    """
    for model, name, ann in _walk(DescriptionDraft):
        for a in _flatten(ann):
            origin = get_origin(a) or a
            assert origin is not dict, f"{model.__name__}.{name} uses dict"
            assert a is not Any, f"{model.__name__}.{name} uses Any"


def test_draft_excludes_server_computed_fields():
    assert SERVER_COMPUTED_FIELDS & set(DescriptionDraft.model_fields) == set()


def test_draft_copied_fields_exist_on_draft():
    assert DRAFT_COPIED_FIELDS <= set(DescriptionDraft.model_fields)


def test_element_fields_equal_draft_copy_plus_server_fields():
    """FR-08: MultimodalElement = Draft 복사 필드 ∪ 서버 필드 (동등 비교)."""
    element_fields = {f.name for f in dc_fields(MultimodalElement)}
    assert element_fields == DRAFT_COPIED_FIELDS | SERVER_COMPUTED_FIELDS


def test_draft_detected_type_is_closed_enum():
    with pytest.raises(Exception):
        DescriptionDraft(
            detected_type="photo",
            description="x",
            keywords=[],
            markdown_table=None,
            chart=None,
            page_text=None,
        )


def test_draft_round_trips_chart():
    d = DescriptionDraft(
        detected_type="chart",
        description="분기별 한도",
        keywords=["한도"],
        markdown_table=None,
        page_text=None,
        chart={
            "chart_type": "bar",
            "x_axis": "분기",
            "y_axis": "억원",
            "series": ["한도"],
            "data_points": [{"label": "1Q", "value": "120"}],
            "trend": "증가",
        },
    )
    assert d.chart is not None and d.chart.data_points[0].value == "120"
