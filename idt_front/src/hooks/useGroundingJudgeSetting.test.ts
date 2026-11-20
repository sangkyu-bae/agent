import { act, renderHook, waitFor } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { ApiError } from '@/services/api/ApiError';
import {
  useGroundingJudgeSetting,
  useUpdateGroundingJudgeSetting,
} from './useGroundingJudgeSetting';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('useGroundingJudgeSetting', () => {
  it('설정과 실제 적용 모델을 조회한다', async () => {
    const { result } = renderHook(() => useGroundingJudgeSetting(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data!.judge_llm_model_id).toBeNull();
    expect(result.current.data!.effective?.source).toBe('env');
  });
});

describe('useUpdateGroundingJudgeSetting', () => {
  it('저장 응답의 실제 적용 모델을 돌려준다', async () => {
    const { result } = renderHook(() => useUpdateGroundingJudgeSetting(), {
      wrapper: createWrapper(),
    });
    let data;
    await act(async () => {
      data = await result.current.mutateAsync({ judge_llm_model_id: 'uuid-2' });
    });
    expect(data).toMatchObject({
      judge_llm_model_id: 'uuid-2',
      effective: { model_name: 'claude-sonnet-4-6', source: 'admin' },
    });
  });

  it('잘못된 모델이면 ApiError(422)로 실패한다', async () => {
    const { result } = renderHook(() => useUpdateGroundingJudgeSetting(), {
      wrapper: createWrapper(),
    });
    await act(async () => {
      await expect(
        result.current.mutateAsync({ judge_llm_model_id: 'uuid-bad' })
      ).rejects.toBeInstanceOf(ApiError);
    });
  });
});
