import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { useExcelPreviewStore } from '@/store/excelPreviewStore';
import { useDocumentPreviewStore } from '@/store/documentPreviewStore';
import { documentExtractorService } from '@/services/documentExtractorService';
import MarkdownRenderer from './MarkdownRenderer';

// Design Ref: document-file-preview §8.2 #1~4 — .docx·.pdf 진입점 (button 모드)
vi.mock('@/services/documentExtractorService', () => ({
  documentExtractorService: { downloadGeneratedFile: vi.fn().mockResolvedValue(undefined) },
}));

const FILE_ID = 'c'.repeat(32);
const link = (name: string) =>
  `다운로드: [${name}](/api/v1/document-extractor/files/${FILE_ID})`;

beforeEach(() => {
  useExcelPreviewStore.setState({ target: null });
  useDocumentPreviewStore.setState({ target: null });
  vi.clearAllMocks();
});

describe('MarkdownRenderer — document-file-preview button 모드', () => {
  it('.docx 산출 링크 옆에 미리보기 버튼을 렌더한다 (FR-01)', () => {
    render(<MarkdownRenderer content={link('보고서.docx')} />);
    expect(screen.getByRole('link', { name: /보고서\.docx/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '보고서.docx 미리보기' })).toBeInTheDocument();
  });

  it('.pdf 버튼 클릭은 문서 스토어만 연다 (FR-02, 다운로드 미발생)', async () => {
    render(<MarkdownRenderer content={link('보고서.pdf')} />);
    await userEvent.click(screen.getByRole('button', { name: '보고서.pdf 미리보기' }));

    expect(useDocumentPreviewStore.getState().target).toEqual({
      fileId: FILE_ID,
      filename: '보고서.pdf',
      kind: 'pdf',
    });
    expect(useExcelPreviewStore.getState().target).toBeNull();
    expect(documentExtractorService.downloadGeneratedFile).not.toHaveBeenCalled();
  });

  it('.docx 버튼은 kind=docx로 연다', async () => {
    render(<MarkdownRenderer content={link('계약서.DOCX')} />);
    await userEvent.click(screen.getByRole('button', { name: '계약서.DOCX 미리보기' }));
    expect(useDocumentPreviewStore.getState().target?.kind).toBe('docx');
  });

  it('.xlsx 버튼은 엑셀 스토어만 연다 (기존 동작 불변)', async () => {
    render(<MarkdownRenderer content={link('수집결과.xlsx')} />);
    await userEvent.click(screen.getByRole('button', { name: '수집결과.xlsx 미리보기' }));
    expect(useExcelPreviewStore.getState().target).toEqual({
      fileId: FILE_ID,
      filename: '수집결과.xlsx',
    });
    expect(useDocumentPreviewStore.getState().target).toBeNull();
  });

  it('.docx 링크 클릭은 다운로드한다', async () => {
    render(<MarkdownRenderer content={link('보고서.docx')} />);
    await userEvent.click(screen.getByRole('link', { name: /보고서\.docx/ }));
    expect(documentExtractorService.downloadGeneratedFile).toHaveBeenCalledWith(
      FILE_ID,
      '보고서.docx',
    );
    expect(useDocumentPreviewStore.getState().target).toBeNull();
  });
});
