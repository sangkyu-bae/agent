"""multimodal-extractor 도메인 VO.

Design Ref: multimodal-extractor §3.1
— 전부 frozen dataclass, 외부 라이브러리 import 없음.
ElementType/ElementStatus 의 value 는 wire 계약(프론트·미리보기 API)이므로 변경 금지.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

OUTPUT_LANGUAGES: tuple[str, ...] = ("ko", "en")
DETAIL_LEVELS: tuple[str, ...] = ("brief", "detailed")


class ElementType(StrEnum):
    FIGURE = "figure"
    CHART = "chart"
    TABLE_IMAGE = "table_image"
    PAGE_SCAN = "page_scan"


class ElementStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class ImageCandidate:
    """추출기가 내놓는 이미지 후보 1건 (Plan FR-01)."""

    page: int
    bbox: BBox
    image_bytes: bytes
    mime: str
    width: int
    height: int
    area_ratio: float
    sha256: str
    hint_type: ElementType

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("page must be >= 1")
        if self.width < 0 or self.height < 0:
            raise ValueError("width/height must be >= 0")
        if not (0.0 <= self.area_ratio <= 1.0):
            raise ValueError("area_ratio must be 0.0~1.0")


@dataclass(frozen=True)
class DataPoint:
    label: str
    value: str  # 단위·통화 보존을 위해 문자열


@dataclass(frozen=True)
class ChartReading:
    chart_type: str | None
    x_axis: str | None
    y_axis: str | None
    series: tuple[str, ...]
    data_points: tuple[DataPoint, ...]
    trend: str | None


@dataclass(frozen=True)
class MultimodalElement:
    """서버 계산 필드 + Draft 복사 필드.

    Plan FR-08 — schemas.SERVER_COMPUTED_FIELDS 와 동기.
    """

    element_id: str
    page: int
    bbox: BBox
    element_type: ElementType
    status: ElementStatus
    reason: str | None
    description: str | None
    keywords: tuple[str, ...]
    markdown_table: str | None
    chart: ChartReading | None
    page_text: str | None
    image_bytes: bytes | None
    mime: str
    width: int
    height: int
    sha256: str
    model_id: str | None
    elapsed_ms: int | None
    degraded_output_mode: bool


@dataclass(frozen=True)
class DroppedCandidate:
    """필터로 제외된 후보 요약 (미리보기 debug 용 — 바이트 미포함)."""

    page: int
    reason: str
    width: int
    height: int


@dataclass(frozen=True)
class ExtractionResult:
    elements: tuple[MultimodalElement, ...]
    total_candidates: int
    dropped_by_filter: int
    skipped_by_limit: int
    succeeded: int
    failed: int
    vision_model_id: str
    provider: str
    model_name: str
    timings_ms: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    # Design §4.2 debug=true: 필터 제외 상세. 바이트는 없으므로 가볍다
    dropped: tuple[DroppedCandidate, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MultimodalSettings:
    """전역 설정 (Plan FR-12) — 범위는 Design §3.1 / API 검증과 동일 숫자."""

    id: str
    enabled: bool
    vision_model_id: str | None
    max_images_per_doc: int
    min_image_px: int
    min_area_ratio: float
    concurrency: int
    timeout_sec: int
    output_language: str
    detail_level: str
    updated_at: datetime

    def __post_init__(self) -> None:
        _require_range("max_images_per_doc", self.max_images_per_doc, 1, 500)
        _require_range("min_image_px", self.min_image_px, 0, 4096)
        _require_range("min_area_ratio", self.min_area_ratio, 0.0, 1.0)
        _require_range("concurrency", self.concurrency, 1, 16)
        _require_range("timeout_sec", self.timeout_sec, 5, 600)
        if self.output_language not in OUTPUT_LANGUAGES:
            raise ValueError(f"output_language must be one of {OUTPUT_LANGUAGES}")
        if self.detail_level not in DETAIL_LEVELS:
            raise ValueError(f"detail_level must be one of {DETAIL_LEVELS}")


def _require_range(name: str, value: float, lo: float, hi: float) -> None:
    if not (lo <= value <= hi):
        raise ValueError(f"{name} must be between {lo} and {hi}")
