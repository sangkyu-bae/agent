import { renderHook, waitFor } from '@testing-library/react';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import {
  useMiddlewareCatalog,
  useSetMiddlewareFlags,
} from '@/hooks/useMiddlewareCatalog';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const CATALOG = {
  middlewares: [
    {
      middleware_type: 'model_retry',
      name: 'LLM 재시도',
      description: 'LLM 호출 실패 시 지수 백오프로 자동 재시도합니다.',
      is_builtin: true,
      is_enforced: false,
      default_config: { max_retries: 3, backoff_factor: 2.0, initial_delay: 1.0 },
      is_active: true,
      sort_order: 10,
    },
    {
      middleware_type: 'model_call_limit',
      name: '모델 호출 상한',
      description: 'run당 LLM 호출 횟수를 제한합니다.',
      is_builtin: false,
      is_enforced: true,
      default_config: { run_limit: 10, exit_behavior: 'end' },
      is_active: true,
      sort_order: 40,
    },
  ],
};

describe('useMiddlewareCatalog', () => {
  it('성공 시 MiddlewareCatalogItem[] 을 반환한다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.MIDDLEWARE_CATALOG}`, () =>
        HttpResponse.json(CATALOG),
      ),
    );
    const { result } = renderHook(() => useMiddlewareCatalog(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(2);
    expect(result.current.data?.[0].middleware_type).toBe('model_retry');
    expect(result.current.data?.[0].is_builtin).toBe(true);
    expect(result.current.data?.[1].is_enforced).toBe(true);
  });

  it('서버 에러 시 isError 가 true 이다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.MIDDLEWARE_CATALOG}`, () =>
        HttpResponse.json({ detail: 'server error' }, { status: 500 }),
      ),
    );
    const { result } = renderHook(() => useMiddlewareCatalog(), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useSetMiddlewareFlags', () => {
  it('PATCH 본문에 부분 갱신 필드만 전송한다', async () => {
    let captured: unknown = null;
    server.use(
      http.patch(
        `*${API_ENDPOINTS.MIDDLEWARE_CATALOG_DETAIL('model_retry')}`,
        async ({ request }) => {
          captured = await request.json();
          return HttpResponse.json({
            ...CATALOG.middlewares[0],
            is_enforced: true,
          });
        },
      ),
    );
    const { result } = renderHook(() => useSetMiddlewareFlags(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({
      middlewareType: 'model_retry',
      body: { is_enforced: true },
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(captured).toEqual({ is_enforced: true });
    expect(result.current.data?.is_enforced).toBe(true);
  });
});
