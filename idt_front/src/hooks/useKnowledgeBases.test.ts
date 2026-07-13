import { renderHook, waitFor } from '@testing-library/react';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import { useKnowledgeBases } from './useKnowledgeBases';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('useKnowledgeBases', () => {
  it('지식베이스 목록을 반환한다', async () => {
    const { result } = renderHook(() => useKnowledgeBases(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(3);
    expect(result.current.data![0].kb_id).toBe('kb-public-1');
    expect(result.current.data![0].scope).toBe('PUBLIC');
    expect(result.current.data![1].collection_name).toBe('admin-coll-01');
  });

  it('API 실패 시 isError가 true이다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.KNOWLEDGE_BASES}`, () =>
        HttpResponse.json({ message: 'Server Error' }, { status: 500 }),
      ),
    );

    const { result } = renderHook(() => useKnowledgeBases(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
