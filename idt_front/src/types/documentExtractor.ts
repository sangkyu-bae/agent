// document-template-extractor Design §7-1: 백엔드 application/document_extractor/schemas.py 와 1:1

export type SlotType = 'value' | 'generated';

export interface TemplateSlot {
  key: string;
  label: string;
  slot_type: SlotType;
  description: string;
  fill_hint: string;
  sample_value: string;
}

export interface ExtractDocumentResponse {
  source_file_id: string;
  source_format: 'pdf' | 'docx';
  html: string;
  // 미리보기 전용 layout HTML (PDF만, 실패/비활성 시 null) — 저장·토큰화 사용 금지 (D1)
  preview_html: string | null;
  suggested_slots: TemplateSlot[];
  // 실제 사용/에코된 변환 MCP 도구 id — 확정 payload에 그대로 동봉 (D5)
  mcp_pdf_to_html_tool_id: string;
  mcp_html_to_doc_tool_id: string;
}

export interface RefineSlotsRequest {
  html: string;
  instruction: string;
  prev_slots: TemplateSlot[];
  regen_count: number;
}

export interface RefineSlotsResponse {
  suggested_slots: TemplateSlot[];
}

// 에이전트 생성/수정 payload에 동봉되는 확정 템플릿 (백엔드 DocumentTemplateRequest)
export interface DocumentTemplateRequest {
  name: string;
  html_skeleton: string;
  slots: TemplateSlot[];
  source_file_id: string;
  source_format: 'pdf' | 'docx';
  mcp_pdf_to_html_tool_id: string;
  mcp_html_to_doc_tool_id: string;
}

/**
 * 빌더 폼이 보유하는 추출 드래프트 (확정 전까지 서버 저장 없음 — stateless).
 * 확정(confirmed=true) 시 htmlSkeleton에 {{key}} 토큰화 결과가 채워진다 (D2).
 */
export interface DocumentExtractorDraft {
  sourceFileId: string;
  sourceFormat: 'pdf' | 'docx';
  html: string;
  // 미리보기 전용 layout HTML — sessionStorage 저장 제외(D7), 복원 시 html 폴백
  previewHtml?: string;
  slots: TemplateSlot[];
  mcpPdfToHtmlToolId: string;
  mcpHtmlToDocToolId: string;
  regenCount: number;
  confirmed: boolean;
  templateName: string;
  htmlSkeleton: string;
}

// ToolCatalog 상 문서추출기 도구 id (내부 도구 prefix 규약)
export const DOCUMENT_EXTRACTOR_TOOL_ID = 'internal:document_extractor';

// 유휴 재추천 주기 (Plan GA3: 미확정 5분 방치 시 재생성)
export const IDLE_RESUGGEST_MS = 5 * 60 * 1000;

// 백엔드 RegenPolicy 상한과 동일 (초과 시 429)
export const MAX_REGEN = 10;
