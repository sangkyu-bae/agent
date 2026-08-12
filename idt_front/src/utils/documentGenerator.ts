// doc-generator Design §5: 드래프트 ↔ 요청/프리필 변환 (순수 함수)
import type {
  DocumentGenerationTypeInfo,
  DocumentGenerationTypeRequest,
  DocumentGeneratorDraft,
} from '@/types/documentGenerator';

/**
 * 드래프트 → 생성/수정 payload.
 * 섹션이 없으면 undefined = 백엔드 "변경 안 함/미등록" (추출기 규약 동형).
 */
export const buildDocumentGenerationTypeRequest = (
  draft: DocumentGeneratorDraft | null | undefined,
  fallbackName: string,
): DocumentGenerationTypeRequest | undefined => {
  if (!draft || draft.sections.length === 0) return undefined;
  return {
    name: draft.name.trim() || fallbackName,
    description: draft.description,
    sections: draft.sections.map((s) => ({
      title: s.title,
      guidance: s.guidance,
    })),
    output_format: draft.outputFormat,
    mcp_html_to_doc_tool_id: draft.mcpHtmlToDocToolId,
  };
};

/** GET detail 프리필 스냅샷 → 폼 드래프트 (FR-12). */
export const draftFromGenerationTypeInfo = (
  info: DocumentGenerationTypeInfo,
): DocumentGeneratorDraft => ({
  name: info.name,
  description: info.description ?? '',
  sections: (info.sections ?? []).map((s) => ({
    title: s.title,
    guidance: s.guidance ?? '',
  })),
  outputFormat: info.output_format === 'pdf' ? 'pdf' : 'docx',
  mcpHtmlToDocToolId: info.mcp_html_to_doc_tool_id ?? '',
});
