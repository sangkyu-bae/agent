// DocumentGeneratorConfigPanel 테스트 (doc-generator Design §5-2·§6)
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { DocumentGeneratorDraft } from '@/types/documentGenerator';
import { PDF_KOREAN_FONT_WARNING } from '@/types/documentGenerator';
import DocumentGeneratorConfigPanel from './DocumentGeneratorConfigPanel';

const draftFixture = (
  overrides: Partial<DocumentGeneratorDraft> = {},
): DocumentGeneratorDraft => ({
  name: '시장조사 보고서',
  description: '시장 동향 조사',
  sections: [
    { title: '개요', guidance: '' },
    { title: '시장 현황', guidance: '웹서치 근거 위주' },
  ],
  outputFormat: 'docx',
  mcpHtmlToDocToolId: '',
  ...overrides,
});

describe('DocumentGeneratorConfigPanel', () => {
  it('null 드래프트면 빈 편집기를 렌더링한다', () => {
    render(<DocumentGeneratorConfigPanel draft={null} onChange={vi.fn()} />);
    expect(screen.getByLabelText('문서 유형명')).toHaveValue('');
    expect(
      screen.getByText(/섹션을 추가해 문서 뼈대를 정의하세요/),
    ).toBeInTheDocument();
  });

  it('드래프트 값을 프리필한다 (FR-12 편집 왕복)', () => {
    render(
      <DocumentGeneratorConfigPanel draft={draftFixture()} onChange={vi.fn()} />,
    );
    expect(screen.getByLabelText('문서 유형명')).toHaveValue('시장조사 보고서');
    expect(screen.getByLabelText('섹션 1 제목')).toHaveValue('개요');
    expect(screen.getByLabelText('섹션 2 지침')).toHaveValue('웹서치 근거 위주');
  });

  it('섹션 추가 시 빈 행이 추가된다', async () => {
    const onChange = vi.fn();
    render(
      <DocumentGeneratorConfigPanel draft={draftFixture()} onChange={onChange} />,
    );
    await userEvent.click(screen.getByRole('button', { name: '+ 섹션 추가' }));
    const next = onChange.mock.calls[0][0] as DocumentGeneratorDraft;
    expect(next.sections).toHaveLength(3);
    expect(next.sections[2]).toEqual({ title: '', guidance: '' });
  });

  it('섹션 삭제가 해당 행만 제거한다', async () => {
    const onChange = vi.fn();
    render(
      <DocumentGeneratorConfigPanel draft={draftFixture()} onChange={onChange} />,
    );
    await userEvent.click(screen.getByRole('button', { name: '섹션 1 삭제' }));
    const next = onChange.mock.calls[0][0] as DocumentGeneratorDraft;
    expect(next.sections.map((s) => s.title)).toEqual(['시장 현황']);
  });

  it('섹션 순서를 아래로 이동할 수 있다', async () => {
    const onChange = vi.fn();
    render(
      <DocumentGeneratorConfigPanel draft={draftFixture()} onChange={onChange} />,
    );
    await userEvent.click(screen.getByRole('button', { name: '섹션 1 아래로' }));
    const next = onChange.mock.calls[0][0] as DocumentGeneratorDraft;
    expect(next.sections.map((s) => s.title)).toEqual(['시장 현황', '개요']);
  });

  it('기본 포맷은 DOCX이고 PDF 경고가 없다 (D4)', () => {
    render(
      <DocumentGeneratorConfigPanel draft={draftFixture()} onChange={vi.fn()} />,
    );
    expect(screen.getByRole('radio', { name: /DOCX/ })).toBeChecked();
    expect(
      screen.queryByText(new RegExp(PDF_KOREAN_FONT_WARNING.slice(0, 10))),
    ).not.toBeInTheDocument();
  });

  it('PDF 선택 시 한글 폰트 경고문이 노출된다 (FR-13)', () => {
    render(
      <DocumentGeneratorConfigPanel
        draft={draftFixture({ outputFormat: 'pdf' })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole('radio', { name: 'PDF' })).toBeChecked();
    expect(
      screen.getByText(new RegExp(PDF_KOREAN_FONT_WARNING.slice(0, 10))),
    ).toBeInTheDocument();
  });

  it('포맷 라디오 전환이 onChange로 전달된다', async () => {
    const onChange = vi.fn();
    render(
      <DocumentGeneratorConfigPanel draft={draftFixture()} onChange={onChange} />,
    );
    await userEvent.click(screen.getByRole('radio', { name: 'PDF' }));
    const next = onChange.mock.calls[0][0] as DocumentGeneratorDraft;
    expect(next.outputFormat).toBe('pdf');
  });

  it('근거 소스 안내문이 표시된다 (FR-11)', () => {
    render(<DocumentGeneratorConfigPanel draft={null} onChange={vi.fn()} />);
    expect(
      screen.getByText(/검색 도구.*함께 선택하면 근거 조사 후 작성/),
    ).toBeInTheDocument();
  });
});
