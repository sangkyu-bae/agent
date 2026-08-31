// golden-sample-blueprint D7 / FR-11 — presentation_generator 워커 설정 (문서생성기 동형).
// 백엔드 PresentationGeneratorConfigRequest / PresentationGeneratorToolConfig 와 동기.

export type PresentationOutputFormat = 'pptx' | 'pdf';

export interface PresentationGeneratorConfigRequest {
  blueprint_id: string;
  output_format: PresentationOutputFormat;
  mcp_pptx_to_pdf_tool_id: string;
  max_slides: number;
}

/** 프론트 보유 드래프트 — 저장 시 presentation_generator 로 전송 */
export interface PresentationGeneratorDraft {
  blueprintId: string;
  outputFormat: PresentationOutputFormat;
  mcpPptxToPdfToolId: string;
  maxSlides: number;
}

/** 카탈로그 표기 tool_id (internal:document_generator 와 동형) */
export const PRESENTATION_GENERATOR_TOOL_ID = 'internal:presentation_generator';

export const MAX_SLIDES_LIMIT = { min: 1, max: 60 } as const;
export const DEFAULT_MAX_SLIDES = 15;

export const EMPTY_PRESENTATION_DRAFT: PresentationGeneratorDraft = {
  blueprintId: '',
  outputFormat: 'pptx',
  mcpPptxToPdfToolId: '',
  maxSlides: DEFAULT_MAX_SLIDES,
};
