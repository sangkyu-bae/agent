"""golden-sample-blueprint API 스키마 (Design §4.2).

요청/응답은 domain serialization(blueprint_to_dict/from_dict) 위에서 동작 —
BlueprintPayload 는 타임스탬프를 제외한 blueprint dict 를 그대로 전달하며 VO 검증이
단일 출처(ValueError → 400).
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.application.blueprint.extraction_use_case import ExtractionOutcome
from src.domain.blueprint.font_normalization import normalize_blueprint_fonts
from src.domain.blueprint.serialization import blueprint_from_dict, blueprint_to_dict
from src.domain.blueprint.value_objects import (
    CURRENT_SCHEMA_VERSION,
    BlueprintAsset,
    DocumentBlueprint,
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RelBoxSchema(_Strict):
    x: float
    y: float
    w: float
    h: float


class SlotSchema(_Strict):
    id: str
    kind: str
    box: RelBoxSchema
    role: str = ""
    max_chars: int | None = None
    max_rows: int | None = None
    asset_id: str | None = None
    align: Literal["left", "center", "right"] = "left"  # schema v2


class DecorationSchema(_Strict):
    """schema v2 — 서버 계산 장식 도형 (blueprint-style-fidelity §4.1)."""

    id: str
    shape: Literal["rect"] = "rect"
    box: RelBoxSchema
    fill: str
    line: str | None = None


class PatternSchema(_Strict):
    id: str
    kind: str
    slots: list[SlotSchema]
    background: str | None = None
    sample_page: int = 0
    notes: str = ""
    decorations: list[DecorationSchema] = []  # schema v2


class TableStyleSchema(_Strict):
    header_bg: str
    header_text: str
    border: str
    zebra: bool
    # blueprint-render-style-fidelity — 선택 필드 (기본값 = 현행 동작)
    zebra_bg: str = "#F3F4F6"
    border_width_pt: float = 0.0


class HeaderFooterSchema(_Strict):
    logo_asset_id: str | None = None
    page_number_format: str = ""
    footer_text: str = ""
    footer_box: RelBoxSchema | None = None  # schema v2
    page_number_box: RelBoxSchema | None = None  # schema v2
    footer_color: str | None = None  # schema v2


class StyleSchema(_Strict):
    slide_size: list[float]
    fonts: dict[str, str]
    sizes: dict[str, float]
    palette: dict[str, str]
    table_style: TableStyleSchema
    header_footer: HeaderFooterSchema
    common_decorations: list[DecorationSchema] = []  # schema v2
    # blueprint-render-style-fidelity — 선택 필드 (기본값 = 현행 동작)
    body_line_spacing: float = 1.0
    body_space_after_pt: float = 0.0
    chart_label_size_pt: float = 0.0
    chart_label_bold: bool = True


class NarrativeSectionSchema(_Strict):
    role: str
    pattern_ids: list[str]
    guidance: str = ""


class NarrativeSchema(_Strict):
    sections: list[NarrativeSectionSchema]
    tone: str = ""
    language: str = "ko"


class AssetSchema(_Strict):
    id: str
    kind: Literal["logo", "decoration", "cover"]
    mime: str
    width: int
    height: int
    sha256: str
    box: RelBoxSchema
    adopted: bool = True
    cover_box: RelBoxSchema | None = None  # schema v2


class BlueprintPayload(_Strict):
    """요청용 blueprint (타임스탬프 없음)."""

    id: str
    name: str = Field(max_length=100)
    description: str = Field(default="", max_length=500)
    source_kind: Literal["pdf", "pptx"]
    page_count: int
    schema_version: int = CURRENT_SCHEMA_VERSION
    style: StyleSchema
    patterns: list[PatternSchema]
    narrative: NarrativeSchema
    assets: list[AssetSchema] = []
    font_mapping: dict[str, str] = {}
    warnings: list[str] = []
    status: Literal["active", "inactive"] = "active"

    def to_domain(self) -> DocumentBlueprint:
        now = datetime.now(UTC).isoformat()
        data = self.model_dump()
        data.update(created_at=now, updated_at=now)
        # Design Ref: blueprint-font-mapping-migration DR-1 — 쓰기 경계 정규화(FR-03).
        return normalize_blueprint_fonts(blueprint_from_dict(data))


class AssetUpload(_Strict):
    id: str
    data_b64: str

    def decode(self) -> bytes:
        return base64.b64decode(self.data_b64)


class BlueprintCreateRequest(_Strict):
    draft: BlueprintPayload
    assets: list[AssetUpload] = []


class BlueprintUpdateRequest(_Strict):
    draft: BlueprintPayload


class BlueprintResponse(BaseModel):
    """저장된 blueprint 전체 (blueprint_to_dict 그대로 + 타임스탬프)."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    status: str
    created_at: str
    updated_at: str

    @classmethod
    def from_domain(cls, bp: DocumentBlueprint) -> BlueprintResponse:
        return cls.model_validate(blueprint_to_dict(bp))


class BlueprintSummary(BaseModel):
    id: str
    name: str
    source_kind: str
    page_count: int
    pattern_count: int
    status: str
    updated_at: str

    @classmethod
    def from_domain(cls, bp: DocumentBlueprint) -> BlueprintSummary:
        return cls(
            id=bp.id,
            name=bp.name,
            source_kind=bp.source_kind,
            page_count=bp.page_count,
            pattern_count=len(bp.patterns),
            status=bp.status,
            updated_at=bp.updated_at.isoformat(),
        )


class AssetPreview(BaseModel):
    id: str
    kind: str
    mime: str
    width: int
    height: int
    box: RelBoxSchema
    adopted: bool
    thumbnail_b64: str | None
    # 저장(POST) 시 클라이언트가 되돌려 보내는 원본 바이트 (추출 응답에만 포함)
    data_b64: str | None = None

    @classmethod
    def from_domain(
        cls, a: BlueprintAsset, thumb: str | None, data: bytes | None = None
    ) -> AssetPreview:
        return cls(
            id=a.id,
            kind=a.kind,
            mime=a.mime,
            width=a.width,
            height=a.height,
            box=RelBoxSchema(x=a.box.x, y=a.box.y, w=a.box.w, h=a.box.h),
            adopted=a.adopted,
            thumbnail_b64=thumb,
            data_b64=base64.b64encode(data).decode("ascii") if data else None,
        )


class ClassificationSummary(BaseModel):
    succeeded: int
    failed: int


class BlueprintExtractResponse(BaseModel):
    draft: BlueprintResponse
    assets: list[AssetPreview]
    page_thumbnails: list[str | None]
    classification: ClassificationSummary
    timings_ms: dict[str, int]

    @classmethod
    def from_outcome(
        cls, out: ExtractionOutcome, thumbnailer: Callable[[bytes], str | None]
    ) -> BlueprintExtractResponse:
        bp = out.blueprint
        return cls(
            draft=BlueprintResponse.from_domain(bp),
            assets=[
                AssetPreview.from_domain(
                    a,
                    thumbnailer(out.assets[a.id]) if a.id in out.assets else None,
                    out.assets.get(a.id),
                )
                for a in bp.assets
            ],
            page_thumbnails=[
                thumbnailer(t) if t else None for t in out.page_thumbnails
            ],
            classification=ClassificationSummary(
                succeeded=out.classification[0], failed=out.classification[1]
            ),
            timings_ms=dict(out.timings_ms),
        )


class FontsResponse(BaseModel):
    installed: list[str]
    default: str


class BlueprintOption(BaseModel):
    id: str
    name: str


class BlueprintOptionsResponse(BaseModel):
    items: list[BlueprintOption]
