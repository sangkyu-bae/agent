import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import type { ReactNode } from 'react';

import { queryClient } from '@/lib/queryClient';
import { server } from '@/__tests__/mocks/server';
import { mockExcelPreview } from '@/__tests__/mocks/handlers';
import { API_ENDPOINTS } from '@/constants/api';
import { useExcelPreviewStore } from '@/store/excelPreviewStore';
import { documentExtractorService } from '@/services/documentExtractorService';
import ExcelPreviewModal from './ExcelPreviewModal';

// 다운로드는 재사용 계약(FR-13)이므로 서비스만 스파이. 프리뷰 조회는 실 MSW 경로.
vi.mock('@/services/documentExtractorService', () => ({
  documentExtractorService: { downloadGeneratedFile: vi.fn().mockResolvedValue(undefined) },
}));

const FILE_ID = 'd'.repeat(32);

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
);

const openModal = () =>
  useExcelPreviewStore.getState().open({ fileId: FILE_ID, filename: '매출현황.xlsx' });

const errorHandler = (status: number, code: string) =>
  http.get(`*${API_ENDPOINTS.DOCUMENT_EXTRACTOR_FILE_PREVIEW(':fileId')}`, () =>
    HttpResponse.json({ detail: { code, message: 'err' } }, { status }),
  );

beforeAll(() => server.listen());
beforeEach(() => {
  useExcelPreviewStore.setState({ target: null });
  vi.clearAllMocks();
});
afterEach(() => {
  server.resetHandlers();
  queryClient.clear();
});
afterAll(() => server.close());

describe('ExcelPreviewModal', () => {
  it('target이 없으면 렌더하지 않는다', () => {
    const { container } = render(<ExcelPreviewModal />, { wrapper });
    expect(container).toBeEmptyDOMElement();
  });

  it('열리면 조회 후 시트 탭·그리드·truncated 안내를 보여준다 (FR-10~11)', async () => {
    openModal();
    render(<ExcelPreviewModal />, { wrapper });

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('tablist')).toBeInTheDocument());
    expect(screen.getAllByRole('tab')).toHaveLength(3);
    expect(screen.getByText('지점')).toBeInTheDocument();
    // Sheet1은 truncated=true → 안내 문구
    expect(screen.getByText(/전체 20,001행 × 3열 중/)).toBeInTheDocument();
  });

  it('탭 전환은 추가 요청 없이 활성 시트를 교체한다', async () => {
    openModal();
    render(<ExcelPreviewModal />, { wrapper });
    await waitFor(() => expect(screen.getByRole('tablist')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('tab', { name: '요약' }));
    expect(screen.getByText('합계')).toBeInTheDocument();
    // 요약 시트는 truncated=false → 안내 미표시
    expect(screen.queryByText(/중 상위/)).not.toBeInTheDocument();
  });

  it('빈 시트는 "데이터 없음"을 보여준다 (FR-11)', async () => {
    openModal();
    render(<ExcelPreviewModal />, { wrapper });
    await waitFor(() => expect(screen.getByRole('tablist')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('tab', { name: '빈시트' }));
    expect(screen.getByText('데이터 없음')).toBeInTheDocument();
  });

  it.each([
    [404, 'FILE_NOT_FOUND', '파일이 만료되었거나 찾을 수 없습니다.', false],
    [403, 'FORBIDDEN', '본인이 생성한 파일만 볼 수 있습니다.', false],
    [415, 'PREVIEW_UNSUPPORTED', '미리보기를 만들 수 없습니다. 파일은 다운로드할 수 있습니다.', true],
    [422, 'PREVIEW_PARSE_FAILED', '미리보기를 만들 수 없습니다. 파일은 다운로드할 수 있습니다.', true],
  ])('%i 오류: 사유 문구와 다운로드 버튼 유무 (FR-11)', async (status, code, message, canDownload) => {
    server.use(errorHandler(status, code));
    openModal();
    render(<ExcelPreviewModal />, { wrapper });

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(message));
    if (canDownload) {
      expect(screen.getByRole('button', { name: '다운로드' })).toBeInTheDocument();
    } else {
      expect(screen.queryByRole('button', { name: '다운로드' })).not.toBeInTheDocument();
    }
  });

  it('네트워크/5xx 오류: 일반 문구 + 다운로드 버튼 유지 (FR-11)', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.DOCUMENT_EXTRACTOR_FILE_PREVIEW(':fileId')}`, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    openModal();
    render(<ExcelPreviewModal />, { wrapper });

    // 훅이 5xx를 1회 재시도하므로 기본보다 긴 타임아웃
    await waitFor(
      () =>
        expect(screen.getByRole('alert')).toHaveTextContent(
          '미리보기를 불러오지 못했습니다. 다시 시도해주세요.',
        ),
      { timeout: 5000 },
    );
    expect(screen.getByRole('button', { name: '다운로드' })).toBeInTheDocument();
  }, 10000);

  it('조회 중 로딩 스피너를 보여준다 (FR-11)', () => {
    openModal();
    render(<ExcelPreviewModal />, { wrapper });
    expect(screen.getByText('미리보기를 불러오는 중…')).toBeInTheDocument();
  });

  it('탭 전환은 네트워크 요청을 추가로 보내지 않는다 (FR-10 전 시트 1회 응답)', async () => {
    let calls = 0;
    server.use(
      http.get(`*${API_ENDPOINTS.DOCUMENT_EXTRACTOR_FILE_PREVIEW(':fileId')}`, ({ params }) => {
        calls += 1;
        return HttpResponse.json(mockExcelPreview(String(params.fileId)));
      }),
    );
    openModal();
    render(<ExcelPreviewModal />, { wrapper });
    await waitFor(() => expect(screen.getByRole('tablist')).toBeInTheDocument());
    expect(calls).toBe(1);

    await userEvent.click(screen.getByRole('tab', { name: '요약' }));
    await userEvent.click(screen.getByRole('tab', { name: 'Sheet1' }));
    expect(calls).toBe(1);
  });

  it('다운로드 실패 시 안내 문구를 보여준다 (G-01)', async () => {
    vi.mocked(documentExtractorService.downloadGeneratedFile).mockRejectedValueOnce(
      new Error('expired'),
    );
    openModal();
    render(<ExcelPreviewModal />, { wrapper });
    await waitFor(() => expect(screen.getByRole('tablist')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: '다운로드' }));
    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        '다운로드에 실패했습니다. 파일이 만료되었을 수 있습니다.',
      ),
    );
    // 실패 후에도 재시도 가능 (버튼 유지)
    expect(screen.getByRole('button', { name: '다운로드' })).toBeEnabled();
  });

  it('다운로드 버튼은 downloadGeneratedFile을 재사용한다 (FR-13)', async () => {
    openModal();
    render(<ExcelPreviewModal />, { wrapper });
    await waitFor(() => expect(screen.getByRole('tablist')).toBeInTheDocument());

    await userEvent.click(screen.getByRole('button', { name: '다운로드' }));
    expect(documentExtractorService.downloadGeneratedFile).toHaveBeenCalledWith(
      FILE_ID,
      '매출현황.xlsx',
    );
  });

  it('닫기 버튼은 스토어를 닫는다', async () => {
    openModal();
    render(<ExcelPreviewModal />, { wrapper });
    await waitFor(() => expect(screen.getByRole('tablist')).toBeInTheDocument());

    // 헤더 X(aria-label="닫기")와 footer "닫기" 둘 다 닫기 — footer(마지막)를 클릭
    const closeButtons = screen.getAllByRole('button', { name: '닫기' });
    await userEvent.click(closeButtons[closeButtons.length - 1]);
    expect(useExcelPreviewStore.getState().target).toBeNull();
  });

  it('ESC로 닫힌다 (접근성 NFR — common Modal 계약)', async () => {
    openModal();
    render(<ExcelPreviewModal />, { wrapper });
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());

    await userEvent.keyboard('{Escape}');
    expect(useExcelPreviewStore.getState().target).toBeNull();
  });
});
