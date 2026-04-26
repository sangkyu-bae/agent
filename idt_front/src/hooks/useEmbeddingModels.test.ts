import { renderHook, waitFor } from '@testing-library/react';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { useEmbeddingModelList } from '@/hooks/useEmbeddingModels';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('useEmbeddingModelList', () => {
  it('모델 목록을 성공적으로 조회한다', async () => {
    const { result } = renderHook(() => useEmbeddingModelList(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.models).toHaveLength(2);
    expect(result.current.data?.total).toBe(2);
    expect(result.current.data?.models[0].model_name).toBe(
      'text-embedding-3-small',
    );
  });

  it('조회 실패 시 isError가 true가 된다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.EMBEDDING_MODELS}`, () =>
        HttpResponse.json({ detail: 'server error' }, { status: 500 }),
      ),
    );

    const { result } = renderHook(() => useEmbeddingModelList(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
