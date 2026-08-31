"""multimodal-extractor Design §3.1 — VO 검증."""

from datetime import datetime

import pytest
from src.domain.multimodal.value_objects import (
    BBox,
    ElementStatus,
    ElementType,
    ImageCandidate,
    MultimodalSettings,
)


def _settings(**over):
    base = dict(
        id="b0000000-0000-4000-8000-000000000001",
        enabled=True,
        vision_model_id="m1",
        max_images_per_doc=50,
        min_image_px=100,
        min_area_ratio=0.02,
        concurrency=4,
        timeout_sec=60,
        output_language="ko",
        detail_level="detailed",
        updated_at=datetime(2026, 8, 21),
    )
    base.update(over)
    return MultimodalSettings(**base)


def test_element_type_wire_values_are_stable():
    assert [e.value for e in ElementType] == [
        "figure",
        "chart",
        "table_image",
        "page_scan",
    ]
    assert [s.value for s in ElementStatus] == ["succeeded", "failed", "skipped"]


def test_settings_defaults_are_valid():
    s = _settings()
    assert s.concurrency == 4 and s.output_language == "ko"


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_images_per_doc", 0),
        ("max_images_per_doc", 501),
        ("min_image_px", -1),
        ("min_image_px", 4097),
        ("min_area_ratio", -0.1),
        ("min_area_ratio", 1.1),
        ("concurrency", 0),
        ("concurrency", 17),
        ("timeout_sec", 4),
        ("timeout_sec", 601),
        ("output_language", "fr"),
        ("detail_level", "verbose"),
    ],
)
def test_settings_rejects_out_of_range(field, value):
    with pytest.raises(ValueError):
        _settings(**{field: value})


def test_settings_is_frozen():
    s = _settings()
    with pytest.raises(Exception):
        s.concurrency = 2  # type: ignore[misc]


def test_image_candidate_holds_geometry_and_hash():
    c = ImageCandidate(
        page=3,
        bbox=BBox(0, 0, 10, 10),
        image_bytes=b"\x89PNG",
        mime="image/png",
        width=200,
        height=100,
        area_ratio=0.3,
        sha256="ab" * 32,
        hint_type=ElementType.FIGURE,
    )
    assert c.page == 3 and c.hint_type is ElementType.FIGURE


def test_image_candidate_rejects_page_below_one():
    with pytest.raises(ValueError):
        ImageCandidate(
            page=0,
            bbox=BBox(0, 0, 1, 1),
            image_bytes=b"x",
            mime="image/png",
            width=1,
            height=1,
            area_ratio=0.0,
            sha256="x",
            hint_type=ElementType.FIGURE,
        )
