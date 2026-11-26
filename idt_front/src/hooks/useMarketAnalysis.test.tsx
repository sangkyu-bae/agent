// stock-analysis-agents module-9 — 실제 authApiClient + MSW 로 접근 판단·오류 코드 경로를 확인한다
// (훅을 vi.mock 하면 ApiError 변환 경로가 가려진다 — idt-front ApiError 인터셉터 교훈).
import { renderHook, waitFor } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import { ApiError } from '@/services/api/ApiError';
import { useMarketAnalysisAccess, useRunNow } from './useMarketAnalysis';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('useMarketAnalysisAccess', () => {
  it('모듈이 꺼져 404 면 권한 없음으로 본다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.MARKET_ANALYSIS_ACCESS}`, () =>
        HttpResponse.json({ detail: 'Not Found' }, { status: 404 }),
      ),
    );
    const { result } = renderHook(() => useMarketAnalysisAccess(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ enabled: false, can_view: false, can_manage: false });
  });

  it('권한 응답을 그대로 돌려준다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.MARKET_ANALYSIS_ACCESS}`, () =>
        HttpResponse.json({ enabled: true, can_view: true, can_manage: false }),
      ),
    );
    const { result } = renderHook(() => useMarketAnalysisAccess(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.data?.can_view).toBe(true));
  });
});

describe('useRunNow', () => {
  it('409 는 ApiError.code 로 온다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.MARKET_ANALYSIS_RUN_NOW}`, () =>
        HttpResponse.json(
          { detail: { code: 'MA_ROUND_RUNNING', message: '실행 중인 회차가 있습니다.' } },
          { status: 409 },
        ),
      ),
    );
    const { result } = renderHook(() => useRunNow(), { wrapper: createWrapper() });
    result.current.mutate('close');
    await waitFor(() => expect(result.current.isError).toBe(true));
    const err = result.current.error;
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe('MA_ROUND_RUNNING');
    expect((err as ApiError).status).toBe(409);
  });
});
