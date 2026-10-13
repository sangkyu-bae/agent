import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { useExcelPreviewStore } from '@/store/excelPreviewStore';
import { documentExtractorService } from '@/services/documentExtractorService';
import MarkdownRenderer from './MarkdownRenderer';

// excel-preview Design §8.3 #1~3 — button 모드(기본 상수) 진입점.
// 기존 MarkdownRenderer.test.tsx는 무수정(additive) — 프리뷰 전용 파일.
vi.mock('@/services/documentExtractorService', () => ({
  documentExtractorService: { downloadGeneratedFile: vi.fn().mockResolvedValue(undefined) },
}));

const FILE_ID = 'a'.repeat(32);
const xlsxLink = `다운로드: [수집결과.xlsx](/api/v1/document-extractor/files/${FILE_ID})`;
const pdfLink = `다운로드: [보고서.pdf](/api/v1/document-extractor/files/${FILE_ID})`;

beforeEach(() => {
  useExcelPreviewStore.setState({ target: null });
  vi.clearAllMocks();
});

describe('MarkdownRenderer — excel-preview button 모드', () => {
  it('.xlsx 산출 링크 옆에 미리보기 버튼을 렌더한다 (FR-08)', () => {
    render(<MarkdownRenderer content={xlsxLink} />);
    expect(screen.getByRole('link', { name: /수집결과\.xlsx/ })).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: '수집결과.xlsx 미리보기' }),
    ).toBeInTheDocument();
  });

  it('미리보기 버튼 클릭은 스토어 open만 호출한다 (다운로드 미발생)', async () => {
    render(<MarkdownRenderer content={xlsxLink} />);
    await userEvent.click(screen.getByRole('button', { name: '수집결과.xlsx 미리보기' }));

    expect(useExcelPreviewStore.getState().target).toEqual({
      fileId: FILE_ID,
      filename: '수집결과.xlsx',
    });
    expect(documentExtractorService.downloadGeneratedFile).not.toHaveBeenCalled();
  });

  it('링크 클릭은 기존대로 다운로드한다 (기존 UX 불변)', async () => {
    render(<MarkdownRenderer content={xlsxLink} />);
    await userEvent.click(screen.getByRole('link', { name: /수집결과\.xlsx/ }));

    expect(documentExtractorService.downloadGeneratedFile).toHaveBeenCalledWith(
      FILE_ID,
      '수집결과.xlsx',
    );
    expect(useExcelPreviewStore.getState().target).toBeNull();
  });

  it('.xlsx 외 산출 링크에는 버튼이 없다 (FR-08)', () => {
    render(<MarkdownRenderer content={pdfLink} />);
    expect(screen.getByRole('link', { name: /보고서\.pdf/ })).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('일반 외부 링크 렌더는 불변이다', () => {
    render(<MarkdownRenderer content={'[문서](https://example.com)'} />);
    const link = screen.getByRole('link', { name: '문서' });
    expect(link).toHaveAttribute('target', '_blank');
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('대문자 확장자(.XLSX)도 버튼을 렌더한다', () => {
    render(
      <MarkdownRenderer
        content={`다운로드: [RESULT.XLSX](/api/v1/document-extractor/files/${FILE_ID})`}
      />,
    );
    expect(screen.getByRole('button', { name: 'RESULT.XLSX 미리보기' })).toBeInTheDocument();
  });
});
