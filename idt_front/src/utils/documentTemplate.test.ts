// document-template-extractor D2 + doc-extractor-preview-highlight D4~D7:
// DOM 정규화 매칭 기반 토큰화/하이라이트 유틸 테스트
import { afterEach, describe, expect, it } from 'vitest';
import {
  buildDocumentTemplateRequest,
  buildPreviewHtml,
  DRAFT_STORAGE_KEY,
  extractPageWidthPt,
  generateSlotKey,
  loadDraftFromSession,
  saveDraftToSession,
  tokenizeHtml,
} from './documentTemplate';
import type {
  DocumentExtractorDraft,
  TemplateSlot,
} from '@/types/documentExtractor';

const slot = (overrides: Partial<TemplateSlot> = {}): TemplateSlot => ({
  key: 'loan_amount',
  label: '여신금액',
  slot_type: 'value',
  description: '',
  fill_hint: '',
  sample_value: '500,000,000원',
  ...overrides,
});

describe('tokenizeHtml', () => {
  it('sample_value 첫 출현을 {{key}} 토큰으로 치환한다', () => {
    const html = '<p>금액: 500,000,000원</p>';
    const result = tokenizeHtml(html, [slot()]);
    expect(result.htmlSkeleton).toBe('<p>금액: {{loan_amount}}</p>');
    expect(result.usedSlots).toHaveLength(1);
    expect(result.missingSlots).toHaveLength(0);
  });

  it('본문에 없는 sample_value 슬롯은 missing으로 분류한다', () => {
    const html = '<p>내용 없음</p>';
    const result = tokenizeHtml(html, [
      slot(),
      slot({ key: 'opinion', label: '소견', sample_value: '' }),
    ]);
    expect(result.usedSlots).toHaveLength(0);
    expect(result.missingSlots.map((s) => s.key)).toEqual([
      'loan_amount',
      'opinion',
    ]);
    expect(result.htmlSkeleton).toBe(html);
  });

  it('동일 sample_value 중복 출현 시 첫 번째만 치환한다', () => {
    const html = '<p>500,000,000원 / 재확인 500,000,000원</p>';
    const result = tokenizeHtml(html, [slot()]);
    expect(result.htmlSkeleton).toBe(
      '<p>{{loan_amount}} / 재확인 500,000,000원</p>',
    );
  });

  // ── D4: PyMuPDF pdf_to_html 출력 특성 대응 (PoC 실측 기반) ──
  it('숫자 엔티티로 이스케이프된 한글도 매칭한다 (PyMuPDF 출력)', () => {
    // 실측: &#xae08;=금, &#xc6d0;=원 — 문자열 완전일치로는 불가능
    const html =
      '<p><span>&#xae08; 500,000,000&#xc6d0;</span></p>';
    const result = tokenizeHtml(html, [
      slot({ sample_value: '금 500,000,000원' }),
    ]);
    expect(result.usedSlots).toHaveLength(1);
    expect(result.htmlSkeleton).toContain('{{loan_amount}}');
  });

  it('여러 span으로 분절된 텍스트도 매칭한다', () => {
    const html = '<p><span>500,</span><span>000,000원</span></p>';
    const result = tokenizeHtml(html, [slot()]);
    expect(result.usedSlots).toHaveLength(1);
    expect(result.htmlSkeleton).toContain('{{loan_amount}}');
    expect(result.htmlSkeleton).not.toContain('000,000원');
  });

  it('연속 공백이 있어도 정규화하여 매칭한다 (white-space:pre)', () => {
    const html = '<p>금   500,000,000원</p>';
    const result = tokenizeHtml(html, [
      slot({ sample_value: '금 500,000,000원' }),
    ]);
    expect(result.usedSlots).toHaveLength(1);
    expect(result.htmlSkeleton).toContain('{{loan_amount}}');
  });

  it('전체 문서(html 태그 포함) 입력은 문서 형태로 직렬화한다', () => {
    const html =
      '<!DOCTYPE html>\n<html><head><meta charset="utf-8"></head>' +
      '<body><p>500,000,000원</p></body></html>';
    const result = tokenizeHtml(html, [slot()]);
    expect(result.htmlSkeleton).toContain('<html>');
    expect(result.htmlSkeleton).toContain('{{loan_amount}}');
  });
});

describe('buildPreviewHtml', () => {
  it('토큰을 라벨 하이라이트로 표시한다', () => {
    const { html } = buildPreviewHtml('<p>{{loan_amount}}</p>', [slot()]);
    expect(html).toContain('<mark');
    expect(html).toContain('여신금액');
    expect(html).not.toContain('{{loan_amount}}');
  });

  it('미확정 원본 html은 sample_value를 하이라이트한다', () => {
    const { html, missingSlotKeys } = buildPreviewHtml(
      '<p>500,000,000원</p>',
      [slot()],
    );
    expect(html).toContain('<mark');
    expect(html).toContain('500,000,000원');
    expect(missingSlotKeys).toEqual([]);
  });

  it('엔티티/분절 텍스트도 하이라이트한다 (D4)', () => {
    const html =
      '<p><span>&#xae08; 500,</span><span>000,000&#xc6d0;</span></p>';
    const result = buildPreviewHtml(html, [
      slot({ sample_value: '금 500,000,000원' }),
    ]);
    expect(result.html).toContain('data-slot="loan_amount"');
    expect(result.missingSlotKeys).toEqual([]);
  });

  it('매칭 실패 슬롯은 missingSlotKeys로 보고한다 (FR-06)', () => {
    const result = buildPreviewHtml('<p>내용 없음</p>', [
      slot(),
      slot({ key: 'date', label: '신청일자', sample_value: '내용' }),
    ]);
    expect(result.missingSlotKeys).toEqual(['loan_amount']);
  });

  it('mark 가시성 스타일을 주입한다 (D5 — layout 투명 텍스트 대응)', () => {
    const { html } = buildPreviewHtml('<p>500,000,000원</p>', [slot()]);
    expect(html).toContain('<style>');
    expect(html).toContain('color: #111 !important');
  });

  it('scale 옵션으로 축소 transform을 주입한다 (D6)', () => {
    const { html } = buildPreviewHtml('<p>x</p>', [], {
      scale: 0.5,
      pageWidthPx: 793,
    });
    expect(html).toContain('transform: scale(0.5)');
    expect(html).toContain('width: 793px');
  });

  it('scale >= 1이면 transform을 주입하지 않는다', () => {
    const { html } = buildPreviewHtml('<p>x</p>', [], { scale: 1 });
    expect(html).not.toContain('transform: scale');
  });
});

describe('extractPageWidthPt (D6)', () => {
  it('PyMuPDF 페이지 div의 pt 폭을 파싱한다', () => {
    const html =
      '<div id="page0" style="width:595.0pt;height:842.0pt"><p>x</p></div>';
    expect(extractPageWidthPt(html)).toBe(595);
  });

  it('layout 모드 pdf-page div도 파싱한다', () => {
    const html =
      '<div class="pdf-page" style="width:612pt;height:792pt">x</div>';
    expect(extractPageWidthPt(html)).toBe(612);
  });

  it('pt 폭이 없으면 null을 반환한다', () => {
    expect(extractPageWidthPt('<p>no page</p>')).toBeNull();
  });
});

describe('buildDocumentTemplateRequest', () => {
  const draft: DocumentExtractorDraft = {
    sourceFileId: 'f'.repeat(32),
    sourceFormat: 'pdf',
    html: '<p>500,000,000원</p>',
    slots: [slot()],
    mcpPdfToHtmlToolId: 'mcp_p2h',
    mcpHtmlToDocToolId: 'mcp_h2d',
    regenCount: 1,
    confirmed: true,
    templateName: '여신심의서',
    htmlSkeleton: '<p>{{loan_amount}}</p>',
  };

  it('확정 드래프트를 payload로 변환한다', () => {
    const payload = buildDocumentTemplateRequest(draft, 'fallback');
    expect(payload).toEqual({
      name: '여신심의서',
      html_skeleton: '<p>{{loan_amount}}</p>',
      slots: draft.slots,
      source_file_id: 'f'.repeat(32),
      source_format: 'pdf',
      mcp_pdf_to_html_tool_id: 'mcp_p2h',
      mcp_html_to_doc_tool_id: 'mcp_h2d',
    });
  });

  it('미확정/null 드래프트는 undefined를 반환한다 (변경 안 함)', () => {
    expect(buildDocumentTemplateRequest(null, 'x')).toBeUndefined();
    expect(
      buildDocumentTemplateRequest({ ...draft, confirmed: false }, 'x'),
    ).toBeUndefined();
  });

  it('템플릿 이름이 비면 fallback 이름을 쓴다', () => {
    const payload = buildDocumentTemplateRequest(
      { ...draft, templateName: '' },
      '심의서봇',
    );
    expect(payload?.name).toBe('심의서봇');
  });
});

describe('generateSlotKey', () => {
  it('기존 key와 겹치지 않는 custom_N을 생성한다', () => {
    expect(generateSlotKey([])).toBe('custom_1');
    expect(generateSlotKey(['custom_1', 'custom_2'])).toBe('custom_3');
    expect(generateSlotKey(['custom_1', 'custom_3'])).toBe('custom_2');
  });

  it('생성 key는 백엔드 SLOT_KEY_PATTERN을 만족한다', () => {
    const key = generateSlotKey(['loan_amount']);
    expect(key).toMatch(/^[a-z][a-z0-9_]{0,49}$/);
  });
});

describe('sessionStorage 드래프트 (R4)', () => {
  afterEach(() => sessionStorage.clear());

  const draft: DocumentExtractorDraft = {
    sourceFileId: 'f'.repeat(32),
    sourceFormat: 'pdf',
    html: '<p>500,000,000원</p>',
    slots: [slot()],
    mcpPdfToHtmlToolId: 'mcp_p2h',
    mcpHtmlToDocToolId: 'mcp_h2d',
    regenCount: 0,
    confirmed: false,
    templateName: '여신심의서',
    htmlSkeleton: '',
  };

  it('저장 후 로드하면 동일 드래프트를 반환한다', () => {
    saveDraftToSession(draft);
    expect(loadDraftFromSession()).toEqual(draft);
  });

  it('previewHtml은 저장에서 제외한다 (D7 — 5MB 한계 방어)', () => {
    saveDraftToSession({ ...draft, previewHtml: '<div>large layout</div>' });
    const restored = loadDraftFromSession();
    expect(restored?.previewHtml).toBeUndefined();
    expect(restored?.html).toBe(draft.html);
  });

  it('null 저장 시 스토리지에서 제거한다', () => {
    saveDraftToSession(draft);
    saveDraftToSession(null);
    expect(sessionStorage.getItem(DRAFT_STORAGE_KEY)).toBeNull();
    expect(loadDraftFromSession()).toBeNull();
  });

  it('비어있으면 null을 반환한다', () => {
    expect(loadDraftFromSession()).toBeNull();
  });
});
