// Design Ref: document-file-preview §8.2 #6~12, #14 — 문서 미리보기 모달 상태
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { ApiError } from '@/services/api/ApiError';
import { documentExtractorService } from '@/services/documentExtractorService';
import { useDocumentPreviewStore, type DocumentPreviewTarget } from '@/store/documentPreviewStore';
import { renderDocx } from '@/lib/docxRenderer';
import DocumentPreviewModal from './DocumentPreviewModal';

vi.mock('@/services/documentExtractorService', () => ({
  documentExtractorService: {
    fetchGeneratedFileBlob: vi.fn(),
    downloadGeneratedFile: vi.fn().mockResolvedValue(undefined),
  },
}));

// jsdom은 docx를 그릴 수 없으므로 렌더 경계만 mock (Design §1.2)
vi.mock('@/lib/docxRenderer', () => ({ renderDocx: vi.fn() }));

// 크기 상한을 작게 고정해 큰 Blob 없이 초과 경로를 검증한다
vi.mock('@/types/filePreview', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/types/filePreview')>()),
  DOCX_PREVIEW_MAX_BYTES: 8,
}));

const fetchBlob = vi.mocked(documentExtractorService.fetchGeneratedFileBlob);
const download = vi.mocked(documentExtractorService.downloadGeneratedFile);
const render_ = vi.mocked(renderDocx);

const FILE_ID = 'e'.repeat(32);
const docx: DocumentPreviewTarget = { fileId: FILE_ID, filename: '보고서.docx', kind: 'docx' };
const pdf: DocumentPreviewTarget = { fileId: FILE_ID, filename: '보고서.pdf', kind: 'pdf' };

const renderModal = () => {
  // retryDelay 0: 훅의 5xx 1회 재시도를 실제 지연 없이 검증 (analysis G-10)
  const client = new QueryClient({ defaultOptions: { queries: { retryDelay: 0 } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(<DocumentPreviewModal />, { wrapper });
};

beforeEach(() => {
  useDocumentPreviewStore.setState({ target: null });
  vi.stubGlobal(
    'URL',
    Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() }),
  );
  vi.spyOn(console, 'warn').mockImplementation(() => {});
});
afterEach(() => {
  vi.clearAllMocks();
});

describe('DocumentPreviewModal', () => {
  it('target이 없으면 아무것도 렌더하지 않는다', () => {
    const { container } = renderModal();
    expect(container).toBeEmptyDOMElement();
  });

  it('404는 만료 문구, 다운로드 버튼 없음', async () => {
    fetchBlob.mockRejectedValue(new ApiError('gone', 404));
    useDocumentPreviewStore.getState().open(docx);
    renderModal();
    expect(await screen.findByText('파일이 만료되었거나 찾을 수 없습니다.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '다운로드' })).not.toBeInTheDocument();
  });

  it('403은 소유자 문구, 다운로드 버튼 없음', async () => {
    fetchBlob.mockRejectedValue(new ApiError('no', 403));
    useDocumentPreviewStore.getState().open(pdf);
    renderModal();
    expect(await screen.findByText('본인이 생성한 파일만 볼 수 있습니다.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '다운로드' })).not.toBeInTheDocument();
  });

  it('500은 재시도 문구, 다운로드 버튼 있음', async () => {
    fetchBlob.mockRejectedValue(new ApiError('boom', 500));
    useDocumentPreviewStore.getState().open(docx);
    renderModal();
    // 5xx는 훅 정책상 1회 재시도 후 실패한다
    expect(
      await screen.findByText('미리보기를 불러오지 못했습니다. 다시 시도해주세요.'),
    ).toBeInTheDocument();
    expect(fetchBlob).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('button', { name: '다운로드' })).toBeInTheDocument();
  });

  it('docx 성공: renderDocx를 Blob·ShadowRoot로 1회 호출하고 로딩이 사라진다', async () => {
    const blob = new Blob(['1234']);
    fetchBlob.mockResolvedValue(blob);
    render_.mockResolvedValue(undefined);
    useDocumentPreviewStore.getState().open(docx);
    renderModal();

    expect(screen.getByText('문서를 불러오는 중…')).toBeInTheDocument();
    await waitFor(() => expect(render_).toHaveBeenCalledTimes(1));
    expect(render_.mock.calls[0][0]).toBe(blob);
    expect(render_.mock.calls[0][1]).toBeInstanceOf(ShadowRoot);
    await waitFor(() =>
      expect(screen.queryByText('문서를 불러오는 중…')).not.toBeInTheDocument(),
    );
    expect(screen.getByText(/원본과 일부 서식이 다를 수 있습니다/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '다운로드' })).toBeInTheDocument();
  });

  it('docx 렌더 실패: 미리보기 불가 문구, 다운로드 버튼 있음', async () => {
    fetchBlob.mockResolvedValue(new Blob(['1234']));
    render_.mockRejectedValue(new Error('bad zip'));
    useDocumentPreviewStore.getState().open(docx);
    renderModal();
    expect(
      await screen.findByText('미리보기를 만들 수 없습니다. 파일은 다운로드할 수 있습니다.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '다운로드' })).toBeInTheDocument();
  });

  it('docx 크기 초과: 크기 문구, renderDocx 미호출', async () => {
    fetchBlob.mockResolvedValue(new Blob(['123456789'])); // 9 bytes > mock 상한 8
    useDocumentPreviewStore.getState().open(docx);
    renderModal();
    expect(
      await screen.findByText('파일이 커서 미리볼 수 없습니다. 다운로드해서 확인해주세요.'),
    ).toBeInTheDocument();
    expect(render_).not.toHaveBeenCalled();
  });

  it('pdf 성공: iframe을 표시한다 (크기 상한 미적용)', async () => {
    fetchBlob.mockResolvedValue(new Blob(['%PDF-1.7 long body']));
    useDocumentPreviewStore.getState().open(pdf);
    renderModal();
    expect(await screen.findByTitle('보고서.pdf 미리보기')).toBeInTheDocument();
    expect(render_).not.toHaveBeenCalled();
  });

  it('다운로드 클릭은 downloadGeneratedFile을 호출하고, 실패 시 안내한다', async () => {
    fetchBlob.mockResolvedValue(new Blob(['%PDF']));
    download.mockRejectedValueOnce(new ApiError('gone', 404));
    useDocumentPreviewStore.getState().open(pdf);
    renderModal();

    await userEvent.click(await screen.findByRole('button', { name: '다운로드' }));
    expect(download).toHaveBeenCalledWith(FILE_ID, '보고서.pdf');
    expect(
      await screen.findByText('다운로드에 실패했습니다. 파일이 만료되었을 수 있습니다.'),
    ).toBeInTheDocument();
  });

  it('닫기 버튼은 스토어를 닫는다', async () => {
    fetchBlob.mockResolvedValue(new Blob(['%PDF']));
    useDocumentPreviewStore.getState().open(pdf);
    renderModal();
    // 헤더 X(aria-label="닫기")와 footer "닫기" 둘 다 닫기 — footer(마지막)를 클릭
    const closeButtons = screen.getAllByRole('button', { name: '닫기' });
    await userEvent.click(closeButtons[closeButtons.length - 1]);
    expect(useDocumentPreviewStore.getState().target).toBeNull();
  });
});
