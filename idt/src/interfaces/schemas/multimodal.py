"""multimodal-extractor 요청/응답 스키마.

Design Ref: multimodal-extractor §4.2
— 범위 숫자는 도메인 VO(MultimodalSettings)와 동일.
응답은 wire 계약(프론트 types/multimodal.ts 와 동기).
ElementType/Status 값은 StrEnum value.
"""

from collections.abc import Callable
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.application.multimodal.settings_use_case import (
    ConnectionTestResult,
    SettingsUpdate,
    SettingsView,
)
from src.domain.llm_model.entity import LlmModel
from src.domain.multimodal.schemas import DescriptionDraft
from src.domain.multimodal.value_objects import (
    ChartReading,
    ExtractionResult,
    MultimodalElement,
)

# ── settings ──────────────────────────────────────────────────────────────────


class MultimodalSettingsRequest(BaseModel):
    """PUT 전체 교체 — 전 필드 필수."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    vision_model_id: str | None = Field(max_length=36)
    max_images_per_doc: int = Field(ge=1, le=500)
    min_image_px: int = Field(ge=0, le=4096)
    min_area_ratio: float = Field(ge=0.0, le=1.0)
    concurrency: int = Field(ge=1, le=16)
    timeout_sec: int = Field(ge=5, le=600)
    output_language: str = Field(pattern="^(ko|en)$")
    detail_level: str = Field(pattern="^(brief|detailed)$")

    def to_update(self) -> SettingsUpdate:
        return SettingsUpdate(**self.model_dump())


class VisionModelSummary(BaseModel):
    id: str
    provider: str
    model_name: str
    display_name: str
    is_active: bool
    supports_vision: bool

    @classmethod
    def from_domain(cls, m: LlmModel) -> "VisionModelSummary":
        return cls(
            id=m.id,
            provider=m.provider,
            model_name=m.model_name,
            display_name=m.display_name,
            is_active=m.is_active,
            supports_vision=m.supports_vision,
        )


class MultimodalSettingsResponse(BaseModel):
    id: str
    enabled: bool
    vision_model_id: str | None
    vision_model: VisionModelSummary | None
    warnings: list[str]
    max_images_per_doc: int
    min_image_px: int
    min_area_ratio: float
    concurrency: int
    timeout_sec: int
    output_language: str
    detail_level: str
    updated_at: datetime

    @classmethod
    def from_view(cls, v: SettingsView) -> "MultimodalSettingsResponse":
        s = v.settings
        return cls(
            id=s.id,
            enabled=s.enabled,
            vision_model_id=s.vision_model_id,
            vision_model=(
                VisionModelSummary.from_domain(v.vision_model)
                if v.vision_model
                else None
            ),
            warnings=list(v.warnings),
            max_images_per_doc=s.max_images_per_doc,
            min_image_px=s.min_image_px,
            min_area_ratio=s.min_area_ratio,
            concurrency=s.concurrency,
            timeout_sec=s.timeout_sec,
            output_language=s.output_language,
            detail_level=s.detail_level,
            updated_at=s.updated_at,
        )


class ConnectionTestResponse(BaseModel):
    ok: bool
    provider: str
    model_name: str
    elapsed_ms: int
    degraded_output_mode: bool
    draft: DescriptionDraft | None
    error: str | None

    @classmethod
    def from_result(cls, r: ConnectionTestResult) -> "ConnectionTestResponse":
        return cls(
            ok=r.ok,
            provider=r.provider,
            model_name=r.model_name,
            elapsed_ms=r.elapsed_ms,
            degraded_output_mode=r.degraded_output_mode,
            draft=r.draft,
            error=r.error,
        )


# ── preview ───────────────────────────────────────────────────────────────────


class BBoxResponse(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class DataPointResponse(BaseModel):
    label: str
    value: str


class ChartReadingResponse(BaseModel):
    chart_type: str | None
    x_axis: str | None
    y_axis: str | None
    series: list[str]
    data_points: list[DataPointResponse]
    trend: str | None

    @classmethod
    def from_domain(cls, c: ChartReading) -> "ChartReadingResponse":
        return cls(
            chart_type=c.chart_type,
            x_axis=c.x_axis,
            y_axis=c.y_axis,
            series=list(c.series),
            data_points=[
                DataPointResponse(label=p.label, value=p.value) for p in c.data_points
            ],
            trend=c.trend,
        )


class MultimodalElementResponse(BaseModel):
    """MultimodalElement 에서 image_bytes 를 제외하고 thumbnail_b64 를 더한 형태.

    Design §7.
    """

    element_id: str
    page: int
    bbox: BBoxResponse
    element_type: str
    status: str
    reason: str | None
    description: str | None
    keywords: list[str]
    markdown_table: str | None
    chart: ChartReadingResponse | None
    page_text: str | None
    mime: str
    width: int
    height: int
    sha256: str
    model_id: str | None
    elapsed_ms: int | None
    degraded_output_mode: bool
    thumbnail_b64: str | None

    @classmethod
    def from_domain(
        cls, e: MultimodalElement, thumb: Callable[[bytes], str | None]
    ) -> "MultimodalElementResponse":
        return cls(
            element_id=e.element_id,
            page=e.page,
            bbox=BBoxResponse(x0=e.bbox.x0, y0=e.bbox.y0, x1=e.bbox.x1, y1=e.bbox.y1),
            element_type=e.element_type.value,
            status=e.status.value,
            reason=e.reason,
            description=e.description,
            keywords=list(e.keywords),
            markdown_table=e.markdown_table,
            chart=ChartReadingResponse.from_domain(e.chart) if e.chart else None,
            page_text=e.page_text,
            mime=e.mime,
            width=e.width,
            height=e.height,
            sha256=e.sha256,
            model_id=e.model_id,
            elapsed_ms=e.elapsed_ms,
            degraded_output_mode=e.degraded_output_mode,
            thumbnail_b64=thumb(e.image_bytes) if e.image_bytes else None,
        )


class DroppedCandidateResponse(BaseModel):
    page: int
    reason: str
    width: int
    height: int


class MultimodalPreviewResponse(BaseModel):
    vision_model_id: str
    provider: str
    model_name: str
    total_candidates: int
    dropped_by_filter: int
    skipped_by_limit: int
    succeeded: int
    failed: int
    timings_ms: dict[str, int]
    elements: list[MultimodalElementResponse]
    # debug=true 일 때만 채움 (None 이면 직렬화에서 제외)
    dropped: list[DroppedCandidateResponse] | None = None

    @classmethod
    def from_result(
        cls,
        r: ExtractionResult,
        thumb: Callable[[bytes], str | None],
        debug: bool,
    ) -> "MultimodalPreviewResponse":
        fields: dict = dict(
            vision_model_id=r.vision_model_id,
            provider=r.provider,
            model_name=r.model_name,
            total_candidates=r.total_candidates,
            dropped_by_filter=r.dropped_by_filter,
            skipped_by_limit=r.skipped_by_limit,
            succeeded=r.succeeded,
            failed=r.failed,
            timings_ms=dict(r.timings_ms),
            elements=[
                MultimodalElementResponse.from_domain(e, thumb) for e in r.elements
            ],
        )
        if (
            debug
        ):  # 미설정(unset) 상태를 유지해야 response_model_exclude_unset 으로 빠진다
            fields["dropped"] = [
                DroppedCandidateResponse(
                    page=d.page, reason=d.reason, width=d.width, height=d.height
                )
                for d in r.dropped
            ]
        return cls(**fields)
