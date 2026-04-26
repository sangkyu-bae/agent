import { renderHook, waitFor } from '@testing-library/react';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { useToolCatalog } from '@/hooks/useToolCatalog';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('useToolCatalog', () => {
  it('성공 시 CatalogTool[] 을 반환한다', async () => {
    const { result } = renderHook(() => useToolCatalog(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(2);
    expect(result.current.data?.[0].tool_id).toBe('internal:excel_export');
    expect(result.current.data?.[0].source).toBe('internal');
    expect(result.current.data?.[1].tool_id).toBe('mcp:srv1:search');
    expect(result.current.data?.[1].source).toBe('mcp');
  });

  it('서버 에러 시 isError 가 true 이다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.TOOL_CATALOG}`, () =>
        HttpResponse.json({ detail: 'server error' }, { status: 500 }),
      ),
    );

    const { result } = renderHook(() => useToolCatalog(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it('빈 목록 응답을 처리한다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.TOOL_CATALOG}`, () =>
        HttpResponse.json({ tools: [] }),
      ),
    );

    const { result } = renderHook(() => useToolCatalog(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(0);
  });
});
