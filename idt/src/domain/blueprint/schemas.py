"""LLM 출력 전용 Draft 스키마 (pydantic).

Design Ref: golden-sample-blueprint §3.1 schemas — LLM 출력 신뢰 경계
(위키 llm-output-trust-boundary / structured-output-strict-schema).
- dict/Any 금지, extra="forbid", 열거는 Literal.
- 서버가 계산하는 필드(id/sample_page 등)는 Draft 에 두지 않는다 —
  DRAFT_PATTERN_COPIED_FIELDS ∪ SERVER_COMPUTED_PATTERN_FIELDS == PagePattern 필드
  를 테스트가 고정한다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PatternKindLiteral = Literal[
    "cover",
    "toc",
    "section_lead",
    "text",
    "chart_with_notes",
    "table",
    "two_column",
    "image_with_notes",
    "closing",
    "unknown",
]
SlotKindLiteral = Literal[
    "title", "text", "bullets", "table", "chart", "image", "footer"
]
ChartTypeLiteral = Literal["bar", "line", "pie"]

# PagePattern 중 Draft 로부터 복사되는 필드 / 서버가 채우는 필드
DRAFT_PATTERN_COPIED_FIELDS: frozenset[str] = frozenset({"kind", "slots", "notes"})
SERVER_COMPUTED_PATTERN_FIELDS: frozenset[str] = frozenset(
    {"id", "background", "sample_page", "decorations"}  # decorations: DR-1 서버 계산
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── 추출: 페이지 분류 ────────────────────────────────────────────────────────


class SlotDraft(_Strict):
    kind: SlotKindLiteral
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)
    role: str
    max_chars: int | None = Field(default=None, gt=0)
    align: Literal["left", "center", "right"] = "left"  # style-fidelity DR-7

    @model_validator(mode="after")
    def _inside(self) -> SlotDraft:
        if self.x + self.w > 1.0 + 1e-9 or self.y + self.h > 1.0 + 1e-9:
            raise ValueError("slot box exceeds slide bounds")
        return self


class PagePatternDraft(_Strict):
    kind: PatternKindLiteral
    slots: list[SlotDraft]
    layout_notes: str


# ── 추출: 서사 종합 ──────────────────────────────────────────────────────────


class NarrativeSectionDraft(_Strict):
    role: str
    pattern_ids: list[str]
    guidance: str


class NarrativeDraft(_Strict):
    sections: list[NarrativeSectionDraft]
    tone: str
    language: Literal["ko", "en"]


# ── 생성: 슬라이드 계획 ──────────────────────────────────────────────────────


class SlidePlanItemDraft(_Strict):
    pattern_id: str
    title: str
    intent: str
    data_hint: str


class SlidePlanDraft(_Strict):
    slides: list[SlidePlanItemDraft]


# ── 생성: 슬롯 내용 ──────────────────────────────────────────────────────────


class ChartSeriesDraft(_Strict):
    name: str
    values: list[float]


class ChartDraft(_Strict):
    type: ChartTypeLiteral
    categories: list[str]
    series: list[ChartSeriesDraft]
    unit: str | None


class TableDraft(_Strict):
    header: list[str]
    rows: list[list[str]]


class SlotContentDraft(_Strict):
    slot_id: str
    text: str | None
    bullets: list[str] | None
    table: TableDraft | None
    chart: ChartDraft | None
    heading: str | None = None  # bullets 소제목 (pptx-font-fidelity FR-03, 선택)


class SlideContentDraft(_Strict):
    slots: list[SlotContentDraft]
