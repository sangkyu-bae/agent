"""domain/blueprint 값 객체.

Design Ref: golden-sample-blueprint §3.1
- D1: 좌표는 슬라이드 비율 0..1 (RelBox). EMU/pt 변환은 infrastructure 렌더러·추출기만.
- 위키 llm-output-trust-boundary: LLM Draft(schemas.py)와 분리된 서버 측 VO.
- 범위 검증은 __post_init__ 가 단일 출처 (DB/ENUM 검증 없음).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Literal

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

SourceKind = Literal["pdf", "pptx"]
BlueprintStatus = Literal["active", "inactive"]
AssetKind = Literal["logo", "decoration", "cover"]
ChartType = Literal["bar", "line", "pie"]

REQUIRED_PALETTE_KEYS: frozenset[str] = frozenset({"primary", "accent1", "text", "bg"})
REQUIRED_SIZE_KEYS: frozenset[str] = frozenset({"h1", "h2", "body", "caption"})
REQUIRED_FONT_KEYS: frozenset[str] = frozenset({"heading", "body"})
OPTIONAL_SIZE_KEYS: frozenset[str] = frozenset({"h3", "subtitle"})
MAX_CHART_SERIES = 6
CURRENT_SCHEMA_VERSION = 2  # blueprint-style-fidelity §3.4 — v1 은 읽기 폴백만
Align = Literal["left", "center", "right"]
_ALIGNS = ("left", "center", "right")
DecorationShape = Literal["rect"]
# 크기 역할 폴백 (Design §3.1): role → (대체 키, 배율) 순서대로 시도
_SIZE_FALLBACKS: dict[str, tuple[tuple[str, float], ...]] = {
    "h3": (("h2", 0.65), ("body", 1.15)),
    "subtitle": (("h1", 0.55), ("body", 1.4)),
}


class PatternKind(StrEnum):
    COVER = "cover"
    TOC = "toc"
    SECTION_LEAD = "section_lead"
    TEXT = "text"
    CHART_WITH_NOTES = "chart_with_notes"
    TABLE = "table"
    TWO_COLUMN = "two_column"
    IMAGE_WITH_NOTES = "image_with_notes"
    CLOSING = "closing"
    UNKNOWN = "unknown"


class SlotKind(StrEnum):
    TITLE = "title"
    TEXT = "text"
    BULLETS = "bullets"
    TABLE = "table"
    CHART = "chart"
    IMAGE = "image"
    FOOTER = "footer"


def _check_hex(name: str, value: str) -> None:
    if not _HEX.match(value):
        raise ValueError(f"{name} must be #RRGGBB, got {value!r}")


# ── 기하 ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RelBox:
    """슬라이드 비율 좌표 (0..1). x+w ≤ 1, y+h ≤ 1, w·h > 0."""

    x: float
    y: float
    w: float
    h: float

    def __post_init__(self) -> None:
        for name in ("x", "y", "w", "h"):
            v = getattr(self, name)
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"RelBox.{name} must be within 0..1, got {v}")
        if self.w <= 0 or self.h <= 0:
            raise ValueError("RelBox.w/h must be > 0")
        if self.x + self.w > 1.0 + 1e-9 or self.y + self.h > 1.0 + 1e-9:
            raise ValueError("RelBox exceeds slide bounds")

    @property
    def area(self) -> float:
        return self.w * self.h


# ── 추출 통계 (추출기 출력, 비영속) ──────────────────────────────────────────


@dataclass(frozen=True)
class TextSpan:
    text: str
    font: str
    size: float
    bold: bool
    color: str
    box: RelBox


@dataclass(frozen=True)
class ImageRef:
    sha256: str
    mime: str
    width: int
    height: int
    box: RelBox
    data: bytes = field(repr=False)


@dataclass(frozen=True)
class FillRect:
    """벡터 채움 사각형 (style-fidelity §3.3 DecorationPolicy 입력)."""

    color: str
    box: RelBox

    def __post_init__(self) -> None:
        _check_hex("FillRect.color", self.color)


@dataclass(frozen=True)
class PageStats:
    number: int
    width: float
    height: float
    spans: tuple[TextSpan, ...]
    images: tuple[ImageRef, ...]
    tables: tuple[RelBox, ...]
    has_text: bool
    render_png: bytes | None = field(default=None, repr=False)
    charts: tuple[RelBox, ...] = ()  # PPTX 네이티브 차트 영역 (D4 분류 힌트)
    fills: tuple[tuple[str, float], ...] = ()  # 벡터 채움 (hex 색, 페이지 면적 비율)
    rects: tuple[FillRect, ...] = ()  # 채움 사각형 (좌표 포함) — 장식 추출 입력


@dataclass(frozen=True)
class SampleStats:
    source_kind: SourceKind
    page_size: tuple[float, float]  # inch
    pages: tuple[PageStats, ...]
    theme_fonts: dict[str, str]


# ── blueprint ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Decoration:
    """내용 없는 장식 도형 (Design DR-1) — LLM 이 채우지 않는다. v2 는 rect 만."""

    id: str
    shape: DecorationShape
    box: RelBox
    fill: str
    line: str | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Decoration.id is required")
        if self.shape != "rect":
            raise ValueError(f"Decoration.shape invalid: {self.shape}")
        _check_hex("Decoration.fill", self.fill)
        if self.line is not None:
            _check_hex("Decoration.line", self.line)


def _check_unique_ids(owner: str, items: tuple, label: str) -> None:
    ids = [i.id for i in items]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{owner}: duplicate {label} ids")


@dataclass(frozen=True)
class Slot:
    id: str
    kind: SlotKind
    box: RelBox
    role: str
    max_chars: int | None
    max_rows: int | None
    asset_id: str | None
    align: Align = "left"

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Slot.id is required")
        if self.align not in _ALIGNS:
            raise ValueError(f"Slot.align invalid: {self.align}")
        for name in ("max_chars", "max_rows"):
            v = getattr(self, name)
            if v is not None and v <= 0:
                raise ValueError(f"Slot.{name} must be > 0")


@dataclass(frozen=True)
class PagePattern:
    id: str
    kind: PatternKind
    slots: tuple[Slot, ...]
    background: str | None
    sample_page: int
    notes: str
    decorations: tuple[Decoration, ...] = ()

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("PagePattern.id is required")
        if not self.slots:
            raise ValueError(f"PagePattern {self.id}: slots must not be empty")
        _check_unique_ids(f"PagePattern {self.id}", self.slots, "slot")
        _check_unique_ids(f"PagePattern {self.id}", self.decorations, "decoration")
        if self.background is not None:
            _check_hex("PagePattern.background", self.background)

    def slot(self, slot_id: str) -> Slot | None:
        return next((s for s in self.slots if s.id == slot_id), None)


@dataclass(frozen=True)
class TableStyle:
    header_bg: str
    header_text: str
    border: str
    zebra: bool
    # blueprint-render-style-fidelity DR-2: 기본값이 곧 현행 동작이다.
    zebra_bg: str = "#F3F4F6"  # 렌더러 상수를 토큰으로 이동 (D-3)
    border_width_pt: float = 0.0  # 0 이면 테두리를 그리지 않는다 (D-3)

    def __post_init__(self) -> None:
        for name in ("header_bg", "header_text", "border", "zebra_bg"):
            _check_hex(f"TableStyle.{name}", getattr(self, name))
        if self.border_width_pt < 0:
            raise ValueError("TableStyle.border_width_pt must be >= 0")


@dataclass(frozen=True)
class HeaderFooter:
    logo_asset_id: str | None
    page_number_format: str
    footer_text: str
    footer_box: RelBox | None = None  # None → 렌더러 폴백 상수
    page_number_box: RelBox | None = None
    footer_color: str | None = None  # None → palette["text"]

    def __post_init__(self) -> None:
        if self.footer_color is not None:
            _check_hex("HeaderFooter.footer_color", self.footer_color)


@dataclass(frozen=True)
class StyleTokens:
    slide_size: tuple[float, float]  # inch (w, h)
    fonts: dict[str, str]
    sizes: dict[str, float]
    palette: dict[str, str]
    table_style: TableStyle
    header_footer: HeaderFooter
    common_decorations: tuple[Decoration, ...] = ()  # 비표지 전 슬라이드 공통
    # blueprint-render-style-fidelity DR-2: 기본값 = 현행 동작 (미설정)
    body_line_spacing: float = 1.0  # 1.0 이면 줄간격을 설정하지 않는다 (D-4)
    body_space_after_pt: float = 0.0  # 0 이면 문단 여백 없음 (D-4)
    chart_label_size_pt: float = 0.0  # 0 이면 데이터 레이블 없음 (D-1)
    chart_label_bold: bool = True  # 레이블 굵기 (D-1)

    def __post_init__(self) -> None:
        if self.body_line_spacing <= 0:
            raise ValueError("StyleTokens.body_line_spacing must be > 0")
        if self.body_space_after_pt < 0 or self.chart_label_size_pt < 0:
            raise ValueError("StyleTokens spacing/label sizes must be >= 0")
        if len(self.slide_size) != 2 or any(v <= 0 for v in self.slide_size):
            raise ValueError("StyleTokens.slide_size must be positive (w, h)")
        _check_unique_ids("StyleTokens", self.common_decorations, "decoration")
        if missing := REQUIRED_FONT_KEYS - set(self.fonts):
            raise ValueError(f"StyleTokens.fonts missing {sorted(missing)}")
        if missing := REQUIRED_SIZE_KEYS - set(self.sizes):
            raise ValueError(f"StyleTokens.sizes missing {sorted(missing)}")
        if missing := REQUIRED_PALETTE_KEYS - set(self.palette):
            raise ValueError(f"StyleTokens.palette missing {sorted(missing)}")
        if any(v <= 0 for v in self.sizes.values()):
            raise ValueError("StyleTokens.sizes must be > 0")
        for k, v in self.palette.items():
            _check_hex(f"StyleTokens.palette[{k}]", v)

    def size(self, role: str) -> float:
        """역할별 폰트 크기 — 옵션 키(h3/subtitle)는 폴백 규칙으로 보간 (DR-4)."""
        if role in self.sizes:
            return self.sizes[role]
        for base, ratio in _SIZE_FALLBACKS.get(role, ()):
            if base in self.sizes:
                return round(self.sizes[base] * ratio, 1)
        raise KeyError(role)


@dataclass(frozen=True)
class NarrativeSection:
    role: str
    pattern_ids: tuple[str, ...]
    guidance: str


@dataclass(frozen=True)
class Narrative:
    sections: tuple[NarrativeSection, ...]
    tone: str
    language: str


@dataclass(frozen=True)
class BlueprintAsset:
    id: str
    kind: AssetKind
    mime: str
    width: int
    height: int
    sha256: str
    box: RelBox
    adopted: bool
    cover_box: RelBox | None = None  # 표지에서의 위치 (logo 전용)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("BlueprintAsset.id is required")
        if self.kind not in ("logo", "decoration", "cover"):
            raise ValueError(f"BlueprintAsset.kind invalid: {self.kind}")


@dataclass(frozen=True)
class DocumentBlueprint:
    id: str
    name: str
    description: str
    schema_version: int
    source_kind: SourceKind
    page_count: int
    style: StyleTokens
    patterns: tuple[PagePattern, ...]
    narrative: Narrative
    assets: tuple[BlueprintAsset, ...]
    font_mapping: dict[str, str]
    warnings: tuple[str, ...]
    status: BlueprintStatus
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("DocumentBlueprint.name is required")
        if self.source_kind not in ("pdf", "pptx"):
            raise ValueError(f"source_kind invalid: {self.source_kind}")
        if self.status not in ("active", "inactive"):
            raise ValueError(f"status invalid: {self.status}")
        self._check_patterns()
        self._check_references()

    def _check_patterns(self) -> None:
        ids = [p.id for p in self.patterns]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate pattern ids")

    def _check_references(self) -> None:
        pattern_ids = {p.id for p in self.patterns}
        asset_ids = {a.id for a in self.assets}
        for section in self.narrative.sections:
            unknown = set(section.pattern_ids) - pattern_ids
            if unknown:
                raise ValueError(
                    f"narrative references unknown patterns {sorted(unknown)}"
                )
        for p in self.patterns:
            for s in p.slots:
                if s.asset_id is not None and s.asset_id not in asset_ids:
                    raise ValueError(
                        f"slot {p.id}.{s.id} references unknown asset {s.asset_id}"
                    )

    def pattern(self, pattern_id: str) -> PagePattern | None:
        return next((p for p in self.patterns if p.id == pattern_id), None)

    def adopted_assets(self) -> tuple[BlueprintAsset, ...]:
        return tuple(a for a in self.assets if a.adopted)


# ── 생성 측 ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChartSpec:
    type: ChartType
    categories: tuple[str, ...]
    series: tuple[tuple[str, tuple[float, ...]], ...]
    unit: str | None

    def __post_init__(self) -> None:
        if self.type not in ("bar", "line", "pie"):
            raise ValueError(f"ChartSpec.type invalid: {self.type}")
        if not self.categories or not self.series:
            raise ValueError("ChartSpec requires categories and series")
        for name, values in self.series:
            if len(values) != len(self.categories):
                raise ValueError(f"ChartSpec series {name!r} length mismatch")


@dataclass(frozen=True)
class TableSpec:
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    def __post_init__(self) -> None:
        if not self.header:
            raise ValueError("TableSpec.header is required")
        for r in self.rows:
            if len(r) != len(self.header):
                raise ValueError("TableSpec row width mismatch")


@dataclass(frozen=True)
class SlotContent:
    slot_id: str
    text: str | None
    bullets: tuple[str, ...] | None
    table: TableSpec | None
    chart: ChartSpec | None
    heading: str | None = None  # bullets 슬롯의 소제목 (pptx-font-fidelity FR-03)


@dataclass(frozen=True)
class SlidePlan:
    index: int
    pattern_id: str
    title: str
    intent: str
    data_hint: str

    def __post_init__(self) -> None:
        if self.index <= 0:
            raise ValueError("SlidePlan.index must be >= 1")
        if not self.pattern_id:
            raise ValueError("SlidePlan.pattern_id is required")


@dataclass(frozen=True)
class SlideContent:
    plan: SlidePlan
    slots: tuple[SlotContent, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class PresentationResult:
    file_id: str
    filename: str
    pdf_file_id: str | None
    slide_count: int
    chart_count: int
    warnings: tuple[str, ...]
    usage: dict[str, int]
