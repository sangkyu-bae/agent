"""노이즈 필터 · 상한 Policy (순수 함수).

Design Ref: multimodal-extractor §3.1, §6.3
— 상한 초과는 '조용한 절단' 금지, skipped 로 결과에 남긴다.
Plan FR-03 (필터), FR-04 (상한).
"""

from dataclasses import dataclass

from src.domain.multimodal.value_objects import (
    DroppedCandidate,
    ElementType,
    ImageCandidate,
    MultimodalSettings,
)


@dataclass(frozen=True)
class FilterOutcome:
    kept: list[ImageCandidate]
    dropped: list[DroppedCandidate]


@dataclass(frozen=True)
class SkippedCandidate:
    candidate: ImageCandidate
    reason: str


@dataclass(frozen=True)
class LimitOutcome:
    to_call: list[ImageCandidate]
    skipped: list[SkippedCandidate]


class NoiseFilterPolicy:
    """크기·면적·해시 중복 필터. PAGE_SCAN(전체 페이지 렌더)은 크기 필터 면제."""

    @staticmethod
    def apply(
        candidates: list[ImageCandidate], settings: MultimodalSettings
    ) -> FilterOutcome:
        kept: list[ImageCandidate] = []
        dropped: list[DroppedCandidate] = []
        seen: set[str] = set()
        for c in candidates:
            reason = _drop_reason(c, settings, seen)
            if reason is None:
                seen.add(c.sha256)
                kept.append(c)
            else:
                dropped.append(DroppedCandidate(c.page, reason, c.width, c.height))
        return FilterOutcome(kept=kept, dropped=dropped)


def _drop_reason(
    c: ImageCandidate, settings: MultimodalSettings, seen: set[str]
) -> str | None:
    if c.sha256 in seen:
        return "duplicate_sha256"
    if c.hint_type is ElementType.PAGE_SCAN:
        return None
    if c.width < settings.min_image_px or c.height < settings.min_image_px:
        return "min_image_px"
    if c.area_ratio < settings.min_area_ratio:
        return "min_area_ratio"
    return None


class LimitPolicy:
    """문서당 비전 호출 상한. 초과분은 호출 없이 skipped(reason=limit:...)."""

    @staticmethod
    def apply(
        candidates: list[ImageCandidate], settings: MultimodalSettings
    ) -> LimitOutcome:
        n = settings.max_images_per_doc
        reason = f"limit:max_images_per_doc={n}"
        return LimitOutcome(
            to_call=list(candidates[:n]),
            skipped=[SkippedCandidate(c, reason) for c in candidates[n:]],
        )
