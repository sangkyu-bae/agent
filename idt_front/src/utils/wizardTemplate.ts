/**
 * 위저드 양식 카드 — 추출 응답 ↔ 추출기 드래프트 변환 (순수 함수).
 *
 * Design Ref: wizard-template-request D2 — 위저드가 만든 템플릿은 스튜디오의
 * `DocumentExtractorDraft` 와 같은 모양으로 보관한다. 핸드오프·sessionStorage
 * 복원·저장 payload 변환(`buildDocumentTemplateRequest`)을 전부 기존 유틸로
 * 처리하기 위해서다. 여기에는 변환 로직만 있고 토큰화는 `tokenizeHtml` 재사용.
 */
import { tokenizeHtml } from './documentTemplate';
import type {
  DocumentExtractorDraft,
  ExtractDocumentResponse,
  TemplateSlot,
} from '@/types/documentExtractor';

/** 파일명에서 확장자를 뗀 템플릿 이름 (FR-08). 빈 결과는 fallback. */
export const templateNameFromFile = (
  fileName: string,
  fallback = '양식',
): string => {
  const base = fileName.trim().replace(/\.(pdf|docx)$/i, '').trim();
  return base || fallback;
};

/** 추출 응답 → 미확정 드래프트. 미리보기 HTML 은 보관하지 않는다 (D6: 카드는 미리보기 없음). */
export const extractResponseToDraft = (
  response: ExtractDocumentResponse,
  fileName: string,
): DocumentExtractorDraft => ({
  sourceFileId: response.source_file_id,
  sourceFormat: response.source_format,
  html: response.html,
  slots: response.suggested_slots,
  mcpPdfToHtmlToolId: response.mcp_pdf_to_html_tool_id,
  mcpHtmlToDocToolId: response.mcp_html_to_doc_tool_id,
  regenCount: 0,
  confirmed: false,
  templateName: templateNameFromFile(fileName),
  htmlSkeleton: '',
});

export type ConfirmTemplateResult =
  | { ok: true; draft: DocumentExtractorDraft; missingSlots: TemplateSlot[] }
  | { ok: false; reason: 'NO_USABLE_SLOTS' };

/**
 * [이대로 사용] — 추천 슬롯을 그대로 토큰화해 확정한다 (FR-08).
 *
 * 스튜디오 패널 `handleConfirm` 과 같은 규칙: 예시값이 본문에 있는 슬롯만
 * 남고, 하나도 없으면 확정 불가. 사용자 수정은 스튜디오의 몫(비목표).
 */
export const confirmTemplateDraft = (
  draft: DocumentExtractorDraft,
): ConfirmTemplateResult => {
  const { htmlSkeleton, usedSlots, missingSlots } = tokenizeHtml(
    draft.html,
    draft.slots,
  );
  if (usedSlots.length === 0) return { ok: false, reason: 'NO_USABLE_SLOTS' };
  return {
    ok: true,
    missingSlots,
    draft: { ...draft, slots: usedSlots, confirmed: true, htmlSkeleton },
  };
};
