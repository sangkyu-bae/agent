import { renderHook, waitFor } from '@testing-library/react';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import { useLlmModels } from './useLlmModels';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('useLlmModels', () => {
  it('모델 목록을 조회한다', async () => {
    const { result } = renderHook(() => useLlmModels(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(2);
    expect(result.current.data![0].model_name).toBe('gpt-4o');
    expect(result.current.data![1].model_name).toBe('claude-sonnet-4-6');
  });

  it('select로 models 배열을 추출한다', async () => {
    const { result } = renderHook(() => useLlmModels(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(Array.isArray(result.current.data)).toBe(true);
    expect(result.current.data![0]).toHaveProperty('provider');
    expect(result.current.data![0]).toHaveProperty('display_name');
  });

  it('초기 상태는 로딩이다', () => {
    const { result } = renderHook(() => useLlmModels(), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(true);
  });

  it('서버 에러 시 isError가 true이다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.LLM_MODELS}`, () =>
        HttpResponse.json({ message: 'Internal Server Error' }, { status: 500 })
      )
    );

    const { result } = renderHook(() => useLlmModels(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
