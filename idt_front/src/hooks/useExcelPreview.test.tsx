import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import type { ReactNode } from 'react';

import { queryClient } from '@/lib/queryClient';
import { server } from '@/__tests__/mocks/server';
import { API_ENDPOINTS } from '@/constants/api';
import { ApiError } from '@/services/api/ApiError';
import { useExcelPreview } from './useExcelPreview';

// excel-preview Design §8.3 #14 — MSW 정상/오류
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
);

const FILE_ID = 'f'.repeat(32);

beforeAll(() => server.listen());
afterEach(() => {
  server.resetHandlers();
  queryClient.clear();
});
afterAll(() => server.close());

describe('useExcelPreview', () => {
  it('fileId가 있으면 프리뷰를 조회한다', async () => {
    const { result } = renderHook(() => useExcelPreview(FILE_ID), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.file_id).toBe(FILE_ID);
    expect(result.current.data?.sheets.length).toBeGreaterThan(0);
    expect(result.current.data?.sheets[0].truncated).toBe(true);
  });

  it('fileId가 null이면 조회하지 않는다 (FR-10 enabled)', () => {
    const { result } = renderHook(() => useExcelPreview(null), { wrapper });
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('5xx는 1회 재시도 후 성공하면 데이터를 반환한다', async () => {
    let calls = 0;
    server.use(
      http.get(`*${API_ENDPOINTS.DOCUMENT_EXTRACTOR_FILE_PREVIEW(':fileId')}`, () => {
        calls += 1;
        if (calls === 1) {
          return HttpResponse.json({ detail: 'boom' }, { status: 500 });
        }
        return HttpResponse.json({
          file_id: FILE_ID, filename: 'x.xlsx', max_rows: 100, max_cols: 50, sheets: [],
        });
      }),
    );
    const { result } = renderHook(() => useExcelPreview(FILE_ID), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 5000 });
    expect(calls).toBe(2);
  }, 10000);

  it('404는 재시도 없이 ApiError(status=404)로 실패한다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.DOCUMENT_EXTRACTOR_FILE_PREVIEW(':fileId')}`, () =>
        HttpResponse.json(
          { detail: { code: 'FILE_NOT_FOUND', message: '만료' } },
          { status: 404 },
        ),
      ),
    );
    const { result } = renderHook(() => useExcelPreview(FILE_ID), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    const err = result.current.error;
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(404);
    expect((err as ApiError).code).toBe('FILE_NOT_FOUND');
  });
});
