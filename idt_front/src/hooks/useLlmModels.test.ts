import { renderHook, waitFor } from '@testing-library/react';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import { ApiError } from '@/services/api/ApiError';
import {
  useLlmModels,
  useCreateLlmModel,
  useUpdateLlmModel,
  useUpdateLlmModelPricing,
  useDeactivateLlmModel,
} from './useLlmModels';

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

  it('includeInactive=true면 비활성 모델을 포함해 조회한다', async () => {
    const { result } = renderHook(() => useLlmModels(true), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(3);
    expect(result.current.data![2].is_active).toBe(false);
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

describe('llm-register 뮤테이션 훅', () => {
  it('H2: useCreateLlmModel 성공 시 모델을 반환하고 목록을 invalidate한다', async () => {
    const wrapper = createWrapper();
    const list = renderHook(() => useLlmModels(), { wrapper });
    await waitFor(() => expect(list.result.current.isSuccess).toBe(true));
    const initialUpdatedAt = list.result.current.dataUpdatedAt;

    const { result } = renderHook(() => useCreateLlmModel(), { wrapper });
    result.current.mutate({
      provider: 'openai',
      model_name: 'gpt-4o-mini',
      display_name: 'GPT-4o mini',
      api_key_env: 'OPENAI_API_KEY',
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data!.id).toBe('uuid-new');
    expect(result.current.data!.model_name).toBe('gpt-4o-mini');
    // 가격은 등록 시점에 설정 불가 → null
    expect(result.current.data!.input_price_per_1k_usd).toBeNull();

    // invalidate → 목록 refetch 발생
    await waitFor(() =>
      expect(list.result.current.dataUpdatedAt).toBeGreaterThan(initialUpdatedAt)
    );
  });

  it('H3: useCreateLlmModel 중복(409) 시 isError이고 ApiError로 detail 메시지에 접근할 수 있다', async () => {
    const { result } = renderHook(() => useCreateLlmModel(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({
      provider: 'openai',
      model_name: 'dup-model',
      display_name: '중복 모델',
      api_key_env: 'OPENAI_API_KEY',
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    // authClient 인터셉터가 detail을 ApiError(message, status)로 정규화한다
    const error = result.current.error as ApiError;
    expect(error.message).toBe('이미 등록된 모델입니다');
    expect(error.status).toBe(409);
  });

  it('H4: useUpdateLlmModel 성공 시 변경 필드가 반영된다', async () => {
    const { result } = renderHook(() => useUpdateLlmModel(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({
      id: 'uuid-1',
      data: { display_name: 'GPT-4o (Updated)', is_default: true },
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data!.display_name).toBe('GPT-4o (Updated)');
    expect(result.current.data!.is_default).toBe(true);
  });

  it('H5: useUpdateLlmModelPricing 성공 시 가격 문자열과 pricing_updated_at이 반영된다', async () => {
    const { result } = renderHook(() => useUpdateLlmModelPricing(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({
      id: 'uuid-1',
      data: { input_price_per_1k_usd: 0.0025, output_price_per_1k_usd: 0.01 },
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data!.input_price_per_1k_usd).toBe('0.0025');
    expect(result.current.data!.output_price_per_1k_usd).toBe('0.01');
    expect(result.current.data!.pricing_updated_at).toBe('2026-07-11T00:00:00');
  });

  it('H6: useDeactivateLlmModel 성공 시 is_active=false를 반환한다', async () => {
    const { result } = renderHook(() => useDeactivateLlmModel(), {
      wrapper: createWrapper(),
    });
    result.current.mutate('uuid-1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data!.is_active).toBe(false);
    expect(result.current.data!.is_default).toBe(false);
  });
});
