import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { useExcelPreviewStore } from '@/store/excelPreviewStore';
import { documentExtractorService } from '@/services/documentExtractorService';
import MarkdownRenderer from './MarkdownRenderer';

// excel-preview Design §8.3 #4 — 'link' 모드 (FR-09).
// 트리거 상수는 vi.mock으로 고정 — 전환이 상수 1곳 변경으로 끝남을 테스트로 보증.
vi.mock('@/types/excelPreview', () => ({
  EXCEL_PREVIEW_TRIGGER: 'link',
}));

vi.mock('@/services/documentExtractorService', () => ({
  documentExtractorService: { downloadGeneratedFile: vi.fn().mockResolvedValue(undefined) },
}));

const FILE_ID = 'b'.repeat(32);
const xlsxLink = `다운로드: [수집결과.xlsx](/api/v1/document-extractor/files/${FILE_ID})`;
const pdfLink = `다운로드: [보고서.pdf](/api/v1/document-extractor/files/${FILE_ID})`;

beforeEach(() => {
  useExcelPreviewStore.setState({ target: null });
  vi.clearAllMocks();
});

describe('MarkdownRenderer — excel-preview link 모드 (FR-09)', () => {
  it('.xlsx 링크 클릭이 프리뷰를 열고 다운로드는 호출하지 않는다', async () => {
    render(<MarkdownRenderer content={xlsxLink} />);
    await userEvent.click(screen.getByRole('link', { name: /수집결과\.xlsx/ }));

    expect(useExcelPreviewStore.getState().target).toEqual({
      fileId: FILE_ID,
      filename: '수집결과.xlsx',
    });
    expect(documentExtractorService.downloadGeneratedFile).not.toHaveBeenCalled();
  });

  it('미리보기 버튼은 렌더하지 않는다 (링크 자체가 진입점)', () => {
    render(<MarkdownRenderer content={xlsxLink} />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('.xlsx 외 링크 클릭은 여전히 다운로드한다', async () => {
    render(<MarkdownRenderer content={pdfLink} />);
    await userEvent.click(screen.getByRole('link', { name: /보고서\.pdf/ }));

    expect(documentExtractorService.downloadGeneratedFile).toHaveBeenCalledWith(
      FILE_ID,
      '보고서.pdf',
    );
    expect(useExcelPreviewStore.getState().target).toBeNull();
  });
});
