import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { useDocumentPreviewStore } from '@/store/documentPreviewStore';
import { documentExtractorService } from '@/services/documentExtractorService';
import MarkdownRenderer from './MarkdownRenderer';

// Design Ref: document-file-preview §8.2 #5 — link 모드에서도 스위치 1곳으로 문서가 따라온다
vi.mock('@/types/filePreview', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/types/filePreview')>()),
  FILE_PREVIEW_TRIGGER: 'link',
}));

vi.mock('@/services/documentExtractorService', () => ({
  documentExtractorService: { downloadGeneratedFile: vi.fn().mockResolvedValue(undefined) },
}));

const FILE_ID = 'd'.repeat(32);

beforeEach(() => {
  useDocumentPreviewStore.setState({ target: null });
  vi.clearAllMocks();
});

describe('MarkdownRenderer — document-file-preview link 모드', () => {
  it('.docx 링크 클릭이 미리보기를 열고 다운로드는 호출하지 않는다', async () => {
    render(
      <MarkdownRenderer
        content={`다운로드: [보고서.docx](/api/v1/document-extractor/files/${FILE_ID})`}
      />,
    );
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: /보고서\.docx/ }));

    expect(useDocumentPreviewStore.getState().target).toEqual({
      fileId: FILE_ID,
      filename: '보고서.docx',
      kind: 'docx',
    });
    expect(documentExtractorService.downloadGeneratedFile).not.toHaveBeenCalled();
  });
});
