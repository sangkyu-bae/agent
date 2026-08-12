// doc-generator 드래프트 ↔ 요청/프리필 변환 테스트
import { describe, expect, it } from 'vitest';
import type { DocumentGeneratorDraft } from '@/types/documentGenerator';
import {
  buildDocumentGenerationTypeRequest,
  draftFromGenerationTypeInfo,
} from './documentGenerator';

const draft = (
  overrides: Partial<DocumentGeneratorDraft> = {},
): DocumentGeneratorDraft => ({
  name: '시장조사 보고서',
  description: '설명',
  sections: [{ title: '개요', guidance: 'g' }],
  outputFormat: 'pdf',
  mcpHtmlToDocToolId: 'mcp_h2d',
  ...overrides,
});

describe('buildDocumentGenerationTypeRequest', () => {
  it('드래프트를 요청 스키마로 변환한다', () => {
    expect(buildDocumentGenerationTypeRequest(draft(), '폴백')).toEqual({
      name: '시장조사 보고서',
      description: '설명',
      sections: [{ title: '개요', guidance: 'g' }],
      output_format: 'pdf',
      mcp_html_to_doc_tool_id: 'mcp_h2d',
    });
  });

  it('이름이 비면 폴백 이름을 사용한다', () => {
    const result = buildDocumentGenerationTypeRequest(
      draft({ name: '  ' }),
      '보고서봇',
    );
    expect(result?.name).toBe('보고서봇');
  });

  it('섹션이 없으면 undefined = 변경 안 함/미등록', () => {
    expect(
      buildDocumentGenerationTypeRequest(draft({ sections: [] }), 'f'),
    ).toBeUndefined();
    expect(buildDocumentGenerationTypeRequest(null, 'f')).toBeUndefined();
    expect(buildDocumentGenerationTypeRequest(undefined, 'f')).toBeUndefined();
  });
});

describe('draftFromGenerationTypeInfo', () => {
  it('detail 스냅샷을 드래프트로 변환한다 (FR-12)', () => {
    expect(
      draftFromGenerationTypeInfo({
        name: '시장조사 보고서',
        description: '설명',
        sections: [{ title: '개요', guidance: 'g' }],
        output_format: 'pdf',
        mcp_html_to_doc_tool_id: 'mcp_h2d',
      }),
    ).toEqual(draft());
  });

  it('결손 필드는 안전한 기본값으로 채운다', () => {
    const result = draftFromGenerationTypeInfo({
      name: 'n',
      description: undefined as unknown as string,
      sections: undefined as unknown as [],
      output_format: 'hwp' as 'docx',
      mcp_html_to_doc_tool_id: undefined as unknown as string,
    });
    expect(result).toEqual({
      name: 'n',
      description: '',
      sections: [],
      outputFormat: 'docx',
      mcpHtmlToDocToolId: '',
    });
  });
});
