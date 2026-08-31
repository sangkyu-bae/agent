// golden-sample-blueprint D7 — 드래프트 ⇄ 요청/워커 tool_config 변환 (순수 함수)
import {
  DEFAULT_MAX_SLIDES,
  MAX_SLIDES_LIMIT,
  type PresentationGeneratorConfigRequest,
  type PresentationGeneratorDraft,
} from '@/types/presentationGenerator';

/** blueprint 미선택이면 undefined (= 전송 안 함 / 변경 안 함) */
export const buildPresentationGeneratorRequest = (
  draft: PresentationGeneratorDraft | null | undefined
): PresentationGeneratorConfigRequest | undefined => {
  if (!draft || !draft.blueprintId) return undefined;
  return {
    blueprint_id: draft.blueprintId,
    output_format: draft.outputFormat,
    mcp_pptx_to_pdf_tool_id: draft.outputFormat === 'pdf' ? draft.mcpPptxToPdfToolId : '',
    max_slides: draft.maxSlides,
  };
};

/** 에이전트 상세의 워커 tool_config → 드래프트 (edit 프리필) */
export const draftFromWorkerToolConfig = (
  toolConfig: Record<string, unknown> | null | undefined
): PresentationGeneratorDraft | null => {
  if (!toolConfig || typeof toolConfig.blueprint_id !== 'string') return null;
  const maxSlides = Number(toolConfig.max_slides);
  return {
    blueprintId: toolConfig.blueprint_id,
    outputFormat: toolConfig.output_format === 'pdf' ? 'pdf' : 'pptx',
    mcpPptxToPdfToolId:
      typeof toolConfig.mcp_pptx_to_pdf_tool_id === 'string'
        ? toolConfig.mcp_pptx_to_pdf_tool_id
        : '',
    maxSlides: Number.isFinite(maxSlides) && maxSlides > 0 ? maxSlides : DEFAULT_MAX_SLIDES,
  };
};

export const validatePresentationDraft = (draft: PresentationGeneratorDraft): string | null => {
  if (!draft.blueprintId) return '양식(blueprint)을 선택하세요.';
  if (draft.maxSlides < MAX_SLIDES_LIMIT.min || draft.maxSlides > MAX_SLIDES_LIMIT.max)
    return `최대 슬라이드 수는 ${MAX_SLIDES_LIMIT.min}~${MAX_SLIDES_LIMIT.max} 사이여야 합니다.`;
  if (draft.mcpPptxToPdfToolId && !draft.mcpPptxToPdfToolId.startsWith('mcp_'))
    return 'PDF 변환 도구 id 는 mcp_ 로 시작해야 합니다.';
  return null;
};
