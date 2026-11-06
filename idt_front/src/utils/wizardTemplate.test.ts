// wizard-template-request Design §8.1 — 추출 응답 ↔ 드래프트 변환 (순수 함수)
import { describe, expect, it } from 'vitest';
import {
  confirmTemplateDraft,
  extractResponseToDraft,
  templateNameFromFile,
} from './wizardTemplate';
import type { ExtractDocumentResponse } from '@/types/documentExtractor';

const response = (over: Partial<ExtractDocumentResponse> = {}): ExtractDocumentResponse => ({
  source_file_id: 'file-1',
  source_format: 'docx',
  html: '<p>회사명: ㅇㅇ상사</p><p>금액: 5억</p>',
  preview_html: '<html>preview</html>',
  suggested_slots: [
    { key: 'company', label: '회사명', slot_type: 'value', description: '법인명', fill_hint: '', sample_value: 'ㅇㅇ상사' },
    { key: 'amount', label: '금액', slot_type: 'value', description: '', fill_hint: '', sample_value: '5억' },
  ],
  mcp_pdf_to_html_tool_id: 'mcp:pdf',
  mcp_html_to_doc_tool_id: 'mcp:doc',
  ...over,
});

describe('templateNameFromFile', () => {
  it('확장자를 떼고 공백을 정리한다', () => {
    expect(templateNameFromFile(' 여신심의서.DOCX ')).toBe('여신심의서');
    expect(templateNameFromFile('form.pdf')).toBe('form');
  });
  it('빈 결과면 fallback', () => {
    expect(templateNameFromFile('.pdf')).toBe('양식');
  });
});

describe('extractResponseToDraft', () => {
  it('미확정 드래프트를 만들고 미리보기는 보관하지 않는다 (D6)', () => {
    const draft = extractResponseToDraft(response(), '여신심의서.docx');
    expect(draft.confirmed).toBe(false);
    expect(draft.htmlSkeleton).toBe('');
    expect(draft.templateName).toBe('여신심의서');
    expect(draft.sourceFileId).toBe('file-1');
    expect(draft.slots).toHaveLength(2);
    expect(draft.previewHtml).toBeUndefined();
    expect(draft.mcpPdfToHtmlToolId).toBe('mcp:pdf');
  });
});

describe('confirmTemplateDraft', () => {
  it('예시값이 본문에 있는 슬롯을 토큰화해 확정한다', () => {
    const result = confirmTemplateDraft(extractResponseToDraft(response(), 'a.docx'));
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.draft.confirmed).toBe(true);
    expect(result.draft.htmlSkeleton).toContain('{{company}}');
    expect(result.draft.htmlSkeleton).toContain('{{amount}}');
    expect(result.draft.slots.map((s) => s.key)).toEqual(['company', 'amount']);
    expect(result.missingSlots).toEqual([]);
  });

  it('본문에 없는 예시값 슬롯은 제외하고 missingSlots 로 알린다', () => {
    const draft = extractResponseToDraft(
      response({
        suggested_slots: [
          { key: 'company', label: '회사명', slot_type: 'value', description: '', fill_hint: '', sample_value: 'ㅇㅇ상사' },
          { key: 'ghost', label: '없는값', slot_type: 'value', description: '', fill_hint: '', sample_value: '존재안함' },
        ],
      }),
      'a.docx',
    );
    const result = confirmTemplateDraft(draft);
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.draft.slots.map((s) => s.key)).toEqual(['company']);
    expect(result.missingSlots.map((s) => s.key)).toEqual(['ghost']);
  });

  it('쓸 수 있는 슬롯이 0개면 NO_USABLE_SLOTS', () => {
    const draft = extractResponseToDraft(
      response({
        suggested_slots: [
          { key: 'ghost', label: '없는값', slot_type: 'value', description: '', fill_hint: '', sample_value: '존재안함' },
        ],
      }),
      'a.docx',
    );
    expect(confirmTemplateDraft(draft)).toEqual({ ok: false, reason: 'NO_USABLE_SLOTS' });
  });
});
