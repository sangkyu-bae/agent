import { describe, expect, it } from 'vitest';
import type { BlueprintDraft } from '@/types/blueprint';
import {
  excludePatterns,
  isAcceptedSampleFile,
  isValidBox,
  validateBlueprintDraft,
} from './blueprintValidators';
import {
  buildPresentationGeneratorRequest,
  draftFromWorkerToolConfig,
  validatePresentationDraft,
} from './presentationGenerator';

const draft = (over: Partial<BlueprintDraft> = {}): BlueprintDraft => ({
  id: 'b',
  name: '샘플',
  description: '',
  source_kind: 'pdf',
  page_count: 1,
  schema_version: 1,
  style: {
    slide_size: [13.333, 7.5],
    fonts: { heading: 'H', body: 'B' },
    sizes: { h1: 28, h2: 20, body: 14, caption: 10 },
    palette: { primary: '#1F3A5F', accent1: '#E07A1F', text: '#222222', bg: '#FFFFFF' },
    table_style: { header_bg: '#1F3A5F', header_text: '#FFFFFF', border: '#CCCCCC', zebra: false },
    header_footer: { logo_asset_id: null, page_number_format: '', footer_text: '' },
  },
  patterns: [
    {
      id: 'p1', kind: 'cover', sample_page: 1, background: null, notes: '',
      slots: [{ id: 't', kind: 'title', box: { x: 0.1, y: 0.1, w: 0.8, h: 0.2 }, role: '', max_chars: 40, max_rows: null, asset_id: null }],
    },
  ],
  narrative: { sections: [{ role: '표지', pattern_ids: ['p1'], guidance: '' }], tone: '', language: 'ko' },
  assets: [],
  font_mapping: {},
  warnings: [],
  status: 'active',
  ...over,
});

describe('blueprintValidators', () => {
  it('유효한 draft 는 오류 없음', () => {
    expect(validateBlueprintDraft(draft())).toEqual([]);
  });

  it('이름·좌표·패턴 id·서사 참조·팔레트 위반을 모두 모은다', () => {
    const bad = draft({
      name: ' ',
      patterns: [
        ...draft().patterns,
        { ...draft().patterns[0], id: 'p1', slots: [{ ...draft().patterns[0].slots[0], box: { x: 0.6, y: 0, w: 0.5, h: 0.5 } }] },
      ],
      narrative: { sections: [{ role: 'x', pattern_ids: ['nope'], guidance: '' }], tone: '', language: 'ko' },
      style: { ...draft().style, palette: { ...draft().style.palette, primary: 'blue' } },
    });
    const errors = validateBlueprintDraft(bad);
    expect(errors.some((e) => e.includes('이름'))).toBe(true);
    expect(errors.some((e) => e.includes('중복'))).toBe(true);
    expect(errors.some((e) => e.includes('0..1'))).toBe(true);
    expect(errors.some((e) => e.includes('nope'))).toBe(true);
    expect(errors.some((e) => e.includes('#RRGGBB'))).toBe(true);
  });

  it('isValidBox 경계', () => {
    expect(isValidBox({ x: 0, y: 0, w: 1, h: 1 })).toBe(true);
    expect(isValidBox({ x: 0.5, y: 0, w: 0.6, h: 1 })).toBe(false);
    expect(isValidBox({ x: 0, y: 0, w: 0, h: 1 })).toBe(false);
  });

  it('isAcceptedSampleFile 은 확장자·크기를 본다', () => {
    expect(isAcceptedSampleFile(new File(['x'], 'a.pdf'))).toBe(true);
    expect(isAcceptedSampleFile(new File(['x'], 'a.PPTX'))).toBe(true);
    expect(isAcceptedSampleFile(new File(['x'], 'a.docx'))).toBe(false);
  });
});

describe('presentationGenerator utils', () => {
  it('blueprint 미선택이면 요청을 만들지 않는다', () => {
    expect(buildPresentationGeneratorRequest(null)).toBeUndefined();
    expect(
      buildPresentationGeneratorRequest({ blueprintId: '', outputFormat: 'pptx', mcpPptxToPdfToolId: '', maxSlides: 5 })
    ).toBeUndefined();
  });

  it('pptx 포맷이면 MCP id 를 비우고 전송한다', () => {
    expect(
      buildPresentationGeneratorRequest({ blueprintId: 'b', outputFormat: 'pptx', mcpPptxToPdfToolId: 'mcp_x', maxSlides: 12 })
    ).toEqual({ blueprint_id: 'b', output_format: 'pptx', mcp_pptx_to_pdf_tool_id: '', max_slides: 12 });
    expect(
      buildPresentationGeneratorRequest({ blueprintId: 'b', outputFormat: 'pdf', mcpPptxToPdfToolId: 'mcp_x', maxSlides: 12 })
    ).toEqual({ blueprint_id: 'b', output_format: 'pdf', mcp_pptx_to_pdf_tool_id: 'mcp_x', max_slides: 12 });
  });

  it('워커 tool_config → 드래프트 (edit 프리필) / 없으면 null', () => {
    expect(draftFromWorkerToolConfig({ blueprint_id: 'b', output_format: 'pdf', mcp_pptx_to_pdf_tool_id: 'mcp_y', max_slides: 8 })).toEqual({
      blueprintId: 'b', outputFormat: 'pdf', mcpPptxToPdfToolId: 'mcp_y', maxSlides: 8,
    });
    expect(draftFromWorkerToolConfig({ blueprint_id: 'b' })).toEqual({
      blueprintId: 'b', outputFormat: 'pptx', mcpPptxToPdfToolId: '', maxSlides: 15,
    });
    expect(draftFromWorkerToolConfig(null)).toBeNull();
    expect(draftFromWorkerToolConfig({ type_id: 't' })).toBeNull();
  });

  it('validatePresentationDraft', () => {
    expect(validatePresentationDraft({ blueprintId: '', outputFormat: 'pptx', mcpPptxToPdfToolId: '', maxSlides: 5 })).toMatch('양식');
    expect(validatePresentationDraft({ blueprintId: 'b', outputFormat: 'pptx', mcpPptxToPdfToolId: '', maxSlides: 0 })).toMatch('슬라이드');
    expect(validatePresentationDraft({ blueprintId: 'b', outputFormat: 'pdf', mcpPptxToPdfToolId: 'x', maxSlides: 5 })).toMatch('mcp_');
    expect(validatePresentationDraft({ blueprintId: 'b', outputFormat: 'pdf', mcpPptxToPdfToolId: 'mcp_x', maxSlides: 5 })).toBeNull();
  });
});

describe('excludePatterns', () => {
  it('제외 패턴과 서사 참조를 함께 제거한다 (빈 목록이면 동일 객체)', () => {
    const d = draft({
      patterns: [draft().patterns[0], { ...draft().patterns[0], id: 'p2' }],
      narrative: { sections: [{ role: 'r', pattern_ids: ['p1', 'p2'], guidance: '' }], tone: '', language: 'ko' },
    });
    expect(excludePatterns(d, [])).toBe(d);
    const out = excludePatterns(d, ['p2']);
    expect(out.patterns.map((p) => p.id)).toEqual(['p1']);
    expect(out.narrative.sections[0].pattern_ids).toEqual(['p1']);
  });
});
