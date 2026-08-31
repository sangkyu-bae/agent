"""LLM 출력 전용 스키마 (DescriptionDraft).

Design Ref: multimodal-extractor §3.1
— LLM 출력 신뢰 경계(위키 llm-output-trust-boundary).
- strict structured output 호환: dict/Any 금지, 전 필드 명시
  (위키 structured-output-strict-schema)
- 서버가 계산하는 필드(status/elapsed_ms/model_id/page/...)는 절대 여기에 두지 않는다.
  SERVER_COMPUTED_FIELDS 와 value_objects.MultimodalElement 는
  테스트로 동등 비교된다 (Plan FR-08).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DetectedType = Literal["figure", "chart", "table_image", "page_scan"]

# MultimodalElement 에서 Draft 로부터 복사되는 필드 집합
DRAFT_COPIED_FIELDS: frozenset[str] = frozenset(
    {"description", "keywords", "markdown_table", "chart", "page_text"}
)

# MultimodalElement 에서 서버가 계산/부여하는 필드 집합 — Draft 에 존재하면 안 된다
SERVER_COMPUTED_FIELDS: frozenset[str] = frozenset(
    {
        "element_id",
        "page",
        "bbox",
        "element_type",
        "status",
        "reason",
        "image_bytes",
        "mime",
        "width",
        "height",
        "sha256",
        "model_id",
        "elapsed_ms",
        "degraded_output_mode",
    }
)


class DraftDataPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(description="데이터 포인트 라벨(예: 1Q, 2024년)")
    value: str = Field(description="값을 단위 포함 문자열로(예: 120억원)")


class DraftChart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chart_type: str | None = Field(description="bar/line/pie 등. 모르면 null")
    x_axis: str | None
    y_axis: str | None
    series: list[str] = Field(description="계열 이름 목록. 없으면 빈 목록")
    data_points: list[DraftDataPoint] = Field(
        description="읽을 수 있는 수치만. 추측 금지"
    )
    trend: str | None = Field(description="추세 한 줄 요약. 판단 불가면 null")


class DescriptionDraft(BaseModel):
    """비전 모델이 채우는 초안. 계산 필드 없음."""

    model_config = ConfigDict(extra="forbid")

    detected_type: DetectedType = Field(description="이미지의 실제 유형 재분류")
    description: str = Field(description="이미지 내용 설명")
    keywords: list[str] = Field(description="검색용 키워드. 없으면 빈 목록")
    markdown_table: str | None = Field(
        description="table_image 일 때 마크다운 표. 아니면 null"
    )
    chart: DraftChart | None = Field(description="chart 일 때 구조화 판독. 아니면 null")
    page_text: str | None = Field(
        description="page_scan 일 때 전사 텍스트. 아니면 null"
    )
