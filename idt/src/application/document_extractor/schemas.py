"""document_extractor 애플리케이션 스키마 (Design §3-1/§3-2).

extract/refine 요청·응답 + 슬롯 DTO(도메인 변환 헬퍼 포함).
"""
from pydantic import BaseModel, Field

from src.domain.document_extractor.schemas import TemplateSlot


class TemplateSlotDto(BaseModel):
    """TemplateSlot의 API 표현. 프론트 타입과 1:1 (api-contract-sync 대상)."""

    key: str
    label: str
    slot_type: str = Field(..., pattern="^(value|generated)$")
    description: str = ""
    fill_hint: str = ""
    sample_value: str = ""

    def to_domain(self) -> TemplateSlot:
        return TemplateSlot(
            key=self.key,
            label=self.label,
            slot_type=self.slot_type,
            description=self.description,
            fill_hint=self.fill_hint,
            sample_value=self.sample_value,
        )

    @classmethod
    def from_domain(cls, slot: TemplateSlot) -> "TemplateSlotDto":
        return cls(
            key=slot.key,
            label=slot.label,
            slot_type=slot.slot_type,
            description=slot.description,
            fill_hint=slot.fill_hint,
            sample_value=slot.sample_value,
        )


class ExtractResponse(BaseModel):
    """POST /document-extractor/extract 응답 (stateless)."""

    source_file_id: str
    source_format: str
    html: str
    # 미리보기 전용 layout HTML (PDF만, 실패/비활성 시 None) — 저장·토큰화 사용 금지 (D1)
    preview_html: str | None = None
    suggested_slots: list[TemplateSlotDto]
    # 실제 사용/에코된 변환 MCP 도구 id — 프론트가 확정 payload에 동봉 (D5)
    mcp_pdf_to_html_tool_id: str
    mcp_html_to_doc_tool_id: str


class RefineRequest(BaseModel):
    """POST /document-extractor/refine 요청."""

    html: str
    instruction: str = Field(..., max_length=1000)
    prev_slots: list[TemplateSlotDto] = []
    regen_count: int = Field(0, ge=0)


class RefineResponse(BaseModel):
    suggested_slots: list[TemplateSlotDto]
