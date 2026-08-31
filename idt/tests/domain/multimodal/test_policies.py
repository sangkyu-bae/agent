"""Design §3.1 / FR-03, FR-04 — 순수 Policy."""

from datetime import datetime

from src.domain.multimodal.policies import LimitPolicy, NoiseFilterPolicy
from src.domain.multimodal.value_objects import (
    BBox,
    ElementType,
    ImageCandidate,
    MultimodalSettings,
)


def _c(page=1, w=300, h=300, area=0.2, sha="a" * 64):
    return ImageCandidate(
        page=page,
        bbox=BBox(0, 0, w, h),
        image_bytes=b"x",
        mime="image/png",
        width=w,
        height=h,
        area_ratio=area,
        sha256=sha,
        hint_type=ElementType.FIGURE,
    )


def _s(**over):
    base = dict(
        id="s",
        enabled=True,
        vision_model_id="m",
        max_images_per_doc=2,
        min_image_px=100,
        min_area_ratio=0.02,
        concurrency=1,
        timeout_sec=10,
        output_language="ko",
        detail_level="brief",
        updated_at=datetime(2026, 1, 1),
    )
    base.update(over)
    return MultimodalSettings(**base)


def test_filter_drops_small_px_and_small_area_and_duplicates():
    cands = [
        _c(sha="1" * 64),
        _c(w=48, h=48, sha="2" * 64),  # min_image_px
        _c(area=0.001, sha="3" * 64),  # min_area_ratio
        _c(page=2, sha="1" * 64),  # duplicate hash (header logo)
        _c(w=150, h=50, sha="4" * 64),  # height < min
    ]
    out = NoiseFilterPolicy.apply(cands, _s())
    assert [c.sha256 for c in out.kept] == ["1" * 64]
    reasons = sorted(d.reason for d in out.dropped)
    assert reasons == [
        "duplicate_sha256",
        "min_area_ratio",
        "min_image_px",
        "min_image_px",
    ]
    assert out.dropped[0].page == 1 and out.dropped[0].width == 48


def test_filter_keeps_first_occurrence_of_duplicate():
    a, b = _c(page=1, sha="9" * 64), _c(page=5, sha="9" * 64)
    out = NoiseFilterPolicy.apply([a, b], _s())
    assert out.kept == [a]


def test_page_scan_candidates_bypass_size_filters():
    """전체 페이지 렌더는 크기/면적 필터 대상이 아니다(항상 크다) — 해시 중복만 적용."""
    scan = ImageCandidate(
        page=1,
        bbox=BBox(0, 0, 1, 1),
        image_bytes=b"x",
        mime="image/png",
        width=10,
        height=10,
        area_ratio=1.0,
        sha256="p" * 64,
        hint_type=ElementType.PAGE_SCAN,
    )
    out = NoiseFilterPolicy.apply([scan], _s())
    assert out.kept == [scan]


def test_limit_marks_overflow_as_skipped_not_dropped():
    cands = [_c(sha=str(i) * 64) for i in range(5)]
    out = LimitPolicy.apply(cands, _s(max_images_per_doc=2))
    assert len(out.to_call) == 2
    assert len(out.skipped) == 3
    assert all(s.reason == "limit:max_images_per_doc=2" for s in out.skipped)
    assert out.skipped[0].candidate is cands[2]
